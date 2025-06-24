import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urlparse
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebScraper:
    def __init__(self):
        self.session = None

    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def extract_daraz_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract specific content from Daraz pages"""
        content = {}
        try:
            # Product title
            title_selectors = [
                '[class*="pdp-title"]',
                '[class*="product-title"]',
                '[class*="item-title"]',
                'h1.title',
                'h1'
            ]
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    content['title'] = title_elem.text.strip()
                    break

            # Price information
            price_selectors = [
                '[class*="pdp-price"]',
                '[class*="product-price"]',
                '[class*="price"]',
                '[data-price]'
            ]
            for selector in price_selectors:
                price_elem = soup.select_one(selector)
                if price_elem:
                    price_text = price_elem.text.strip()
                    # Clean up price text
                    price_text = re.sub(r'[^\d.,]', '', price_text)
                    content['price'] = f"Rs. {price_text}"
                    break

            # Discount information
            discount_selectors = [
                '[class*="discount"]',
                '[class*="off"]',
                '[class*="save"]'
            ]
            for selector in discount_selectors:
                discount_elem = soup.select_one(selector)
                if discount_elem:
                    content['discount'] = discount_elem.text.strip()
                    break

            # Available stock
            stock_selectors = [
                '[class*="quantity"]',
                '[class*="stock"]',
                '[class*="inventory"]'
            ]
            for selector in stock_selectors:
                stock_elem = soup.select_one(selector)
                if stock_elem:
                    content['stock'] = stock_elem.text.strip()
                    break

            # Product rating
            rating_selectors = [
                '[class*="rating"]',
                '[class*="stars"]'
            ]
            for selector in rating_selectors:
                rating_elem = soup.select_one(selector)
                if rating_elem:
                    content['rating'] = rating_elem.text.strip()
                    break

            # Extract date information
            date_selectors = [
                '[class*="time"]',
                '[class*="date"]',
                'time',
                '[datetime]'
            ]
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get('datetime') or date_elem.text
                    try:
                        from datetime import datetime
                        date = datetime.fromisoformat(date_text.strip())
                        content['date'] = date.strftime("%Y-%m-%d")
                    except:
                        content['date'] = date_text.strip()
                    break

        except Exception as e:
            logger.warning(f"Error extracting Daraz content: {str(e)}")

        return content

    async def extract_hamropatro_content(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract specific content from Hamropatro pages"""
        content = {}
        try:
            # Look for tables with price information
            tables = soup.find_all('table')
            for table in tables:
                text = table.get_text()
                if any(keyword in text.lower() for keyword in ['gold', 'silver', 'petrol', 'diesel', 'vegetables']):
                    rows = table.find_all('tr')
                    for row in rows:
                        cols = row.find_all(['td', 'th'])
                        if len(cols) >= 2:
                            key = cols[0].get_text().strip()
                            value = cols[1].get_text().strip()
                            content[key] = value

            # Look for specific price elements
            price_elements = soup.find_all(string=re.compile(r'(?:रु|Rs|NPR|price|rate)', re.IGNORECASE))
            for elem in price_elements:
                parent = elem.parent
                if parent:
                    text = parent.get_text().strip()
                    if any(keyword in text.lower() for keyword in ['gold', 'silver', 'petrol', 'diesel', 'vegetables']):
                        content[text] = text

        except Exception as e:
            logger.warning(f"Error extracting Hamropatro content: {str(e)}")

        return content

    async def scrape_url(self, url: str) -> Optional[Dict[str, str]]:
        """
        Scrape content from a single URL
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/'  # Added referer for better access
        }
        
        try:
            if not self.session:
                await self.init_session()

            timeout = aiohttp.ClientTimeout(total=15)
            async with self.session.get(url, headers=headers, timeout=timeout, ssl=False) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    domain = urlparse(url).netloc.lower()
                    
                    # Extract content based on domain
                    specific_content = {}
                    if 'daraz.com.np' in domain or 'daraz.com' in domain:
                        specific_content = await self.extract_daraz_content(soup)
                        if specific_content:
                            specific_content['source'] = 'Daraz.com.np'
                    elif 'hamropatro.com' in domain:
                        specific_content = await self.extract_hamropatro_content(soup)

                    # Get general content
                    content = self.extract_general_content(soup)
                    
                    # Add timestamp for recency calculation
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    
                    return {
                        'url': url,
                        'content': content,
                        'specific_data': specific_content,
                        'timestamp': specific_content.get('date', timestamp),
                        'domain': domain
                    }
                else:
                    logger.warning(f"Failed to fetch {url}: Status code {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return None

    async def scrape_urls(self, urls: List[str]) -> List[Dict[str, str]]:
        """
        Scrape content from multiple URLs concurrently
        """
        try:
            tasks = [self.scrape_url(url) for url in urls]
            results = await asyncio.gather(*tasks)
            # Filter out None results from failed scrapes
            return [r for r in results if r is not None]
        finally:
            await self.close_session()

    def extract_general_content(self, soup: BeautifulSoup) -> str:
        """Extract general content from any webpage"""
        try:
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'footer', 'iframe', 'aside']):
                tag.decompose()

            # Get main content
            main_content = []
            
            # Try to find main content container with priority order
            content_containers = [
                soup.find('main'),
                soup.find('article'),
                soup.find('div', {'class': re.compile(r'product-detail|pdp-content|item-detail', re.I)}),
                soup.find('div', {'class': re.compile(r'content|main|article', re.I)}),
                soup
            ]
            
            container = next((c for c in content_containers if c is not None), soup)
            
            # Extract text from different elements
            for elem in container.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div.description']):
                text = elem.get_text().strip()
                if len(text) > 20 and not any(x in text.lower() for x in ['cookie', 'privacy policy', 'terms of use']):
                    main_content.append(text)

            return '\n'.join(main_content)

        except Exception as e:
            logger.error(f"Error extracting general content: {str(e)}")
            return ""

    def format_specific_content(self, content: Dict[str, str]) -> str:
        """Format domain-specific content for display"""
        if not content:
            return ""
            
        # Priority order for display
        priority_keys = ['title', 'price', 'discount', 'stock', 'rating', 'date']
        formatted = []
        
        # Add priority items first
        for key in priority_keys:
            if key in content:
                formatted.append(f"{key.title()}: {content[key]}")
        
        # Add any remaining items
        for key, value in content.items():
            if key not in priority_keys:
                formatted.append(f"{key.title()}: {value}")
        
        return '\n'.join(formatted)
