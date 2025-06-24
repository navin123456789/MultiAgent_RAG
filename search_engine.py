from googleapiclient.discovery import build
from typing import List, Dict
import logging
import asyncio
import random
import time
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class SearchEngine:
    def __init__(self):
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        self.gemini_api_key = os.getenv('GOOGLE_AI_STUDIO_KEY')
        
        if not self.api_key or not self.search_engine_id:
            raise ValueError("GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID environment variables are required")
            
        if not self.gemini_api_key:
            raise ValueError("GOOGLE_AI_STUDIO_KEY environment variable is required for Gemini integration")
            
        # Configure Gemini
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
            
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15'
        ]
        
        # Keywords and boost settings
        self.price_keywords = ['price', 'rate', 'cost', 'deal', 'offer', 'discount','purchase']
        self.daraz_boost = 2.0  # Higher boost for daraz.com.np
        self.recency_boost = 1.5  # Boost for recent content
        
        # Social media domains to filter out
        self.filtered_domains = [
            'facebook.com', 'twitter.com', 'instagram.com', 
            'tiktok.com', 'reddit.com', 'linkedin.com',
            'pinterest.com', 'tumblr.com', 'snapchat.com'
        ]

    def calculate_boost(self, url: str, date: str = None) -> float:
        """Calculate relevance boost based on domain and recency"""
        boost = 1.0
        
        # Boost for daraz.com.np domain
        if 'daraz.com.np' in url.lower():
            boost *= self.daraz_boost
            
        # Boost recent content if date is available
        if date:
            try:
                from datetime import datetime
                content_date = datetime.strptime(date, "%Y-%m-%d")
                today = datetime.now()
                days_old = (today - content_date).days
                
                if days_old <= 7:  # Very recent content
                    boost *= self.recency_boost
                elif days_old <= 30:  # Recent month
                    boost *= 1.3
                elif days_old <= 90:  # Last 3 months
                    boost *= 1.1
            except:
                pass
        
        return min(boost, 2.5)  # Cap maximum boost

    async def enhance_with_gemini(self, title: str, snippet: str, query: str) -> Dict[str, str]:
        """Use Gemini to enhance the search result snippet and determine relevance"""
        try:
            prompt = f"""Given the search query: "{query}"
            And this search result:
            Title: {title}
            Content: {snippet}
            
            Please:
            1. Generate a more informative and concise snippet (max 150 words)
            2. Rate the relevance to the query on a scale of 0-1
            3. If the query is about prices or shopping and the content is from daraz.com.np, give it higher relevance
            4. Prioritize recent price information over older content
            
            Format your response as:
            Snippet: [your enhanced snippet]
            Relevance: [score between 0-1]
            """

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            
            # Parse Gemini response
            response_text = response.text
            enhanced_snippet = ''
            relevance = 0.0
            
            for line in response_text.split('\n'):
                if line.startswith('Snippet:'):
                    enhanced_snippet = line.replace('Snippet:', '').strip()
                elif line.startswith('Relevance:'):
                    try:
                        relevance = float(line.replace('Relevance:', '').strip())
                        # Apply boost if it's a price-related query
                        if any(kw in query.lower() for kw in self.price_keywords):
                            boost = self.calculate_boost(snippet)
                            relevance = min(1.0, relevance * boost)
                    except ValueError:
                        relevance = 0.0
            
            return {
                'enhanced_snippet': enhanced_snippet if enhanced_snippet else snippet,
                'relevance': relevance
            }
            
        except Exception as e:
            logger.warning(f"Failed to enhance with Gemini: {str(e)}")
            return {
                'enhanced_snippet': snippet,
                'relevance': 0.5  # Default middle relevance
            }

    async def fetch_page_metadata(self, url: str, user_agent: str) -> Dict[str, str]:
        """Fetch additional metadata from a webpage if needed"""
        try:
            headers = {'User-Agent': user_agent}
            async with asyncio.timeout(10):  # 10 second timeout
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: requests.get(url, headers=headers, timeout=10)
                )
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Get description from meta tag
                description = ''
                meta_desc = soup.find('meta', {'name': ['description', 'Description']})
                if meta_desc and meta_desc.get('content'):
                    description = meta_desc['content']
                
                return {
                    'extra_snippet': description
                }
                
        except Exception as e:
            logger.warning(f"Failed to fetch additional metadata for {url}: {str(e)}")
            return {
                'extra_snippet': ''
            }

    async def search(self, query: str, max_results: int = 15) -> List[Dict[str, str]]:
        """Search for URLs using Google Custom Search API with daraz.com.np prioritization"""
        try:
            if not query.strip():
                logger.warning("Empty query provided")
                return []

            # Clean up query
            original_query = query.strip()
            
            # Modify query to prioritize daraz.com.np for price-related searches
            if any(kw in original_query.lower() for kw in self.price_keywords):
                query = f"{original_query} (site:daraz.com.np OR site:*.com.np)"
            
            results = []
            seen_urls = set()  # To avoid duplicates

            try:
                # Create a service object for Google Custom Search API
                service = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: build('customsearch', 'v1', developerKey=self.api_key)
                )
                
                # Execute search
                search_results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: service.cse().list(
                        q=query,
                        cx=self.search_engine_id,
                        num=min(max_results + 5, 10)  # API limit is 10 per request
                    ).execute()
                )
                
                if "items" not in search_results:
                    logger.warning(f"No results found in API response for query: {query}")
                    return []
                
                user_agent = random.choice(self.user_agents)
                    
                # Process results
                for item in search_results["items"]:
                    if len(results) >= max_results:
                        break
                        
                    url = item.get('link', '')
                    if not url:
                        continue
                        
                    # Skip duplicates and unwanted URLs
                    if url in seen_urls or any(x in url.lower() for x in [
                        '.pdf', '.doc', '.xls', '.jpg', '.png', 
                        'youtube.com'
                    ]):
                        continue
                    
                    # Get title and snippet from API response
                    title = item.get('title', 'Untitled')
                    snippet = item.get('snippet', 'No preview available')
                    
                    # Enhance result with Gemini
                    enhanced = await self.enhance_with_gemini(title, snippet, query)
                    
                    result = {
                        'title': title,
                        'url': url,
                        'snippet': enhanced['enhanced_snippet'],
                        'relevance': enhanced['relevance']
                    }
                        
                    seen_urls.add(url)
                    results.append(result)
                    
                    # Add a small delay between requests to be polite
                    await asyncio.sleep(0.5)
                
                # Sort results by relevance score
                results.sort(key=lambda x: x['relevance'], reverse=True)
                
            except Exception as e:
                logger.error(f"API search error: {str(e)}")
                return []
                    
            if not results:
                logger.warning(f"No results found for query: {query}")
                return []
                
            return results[:max_results]  # Ensure we don't return more than requested
            
        except Exception as e:
            logger.error(f"Error during search: {str(e)}")
            return []
