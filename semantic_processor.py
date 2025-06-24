from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict
import logging
import os
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import re

load_dotenv()
logger = logging.getLogger(__name__)

class SemanticProcessor:
    def __init__(self):
        # Initialize sentence transformer for embeddings
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Configure Gemini
        self.gemini_api_key = os.getenv('GOOGLE_AI_STUDIO_KEY')
        if not self.gemini_api_key:
            raise ValueError("GOOGLE_AI_STUDIO_KEY environment variable is required")
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for a list of texts"""
        return self.encoder.encode(texts, convert_to_numpy=True)

    def compute_similarity(self, query_embedding: np.ndarray, doc_embeddings: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query and documents"""
        return np.dot(doc_embeddings, query_embedding.T) / (
            np.linalg.norm(doc_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

    async def rank_documents(self, query: str, documents: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Rank documents using Gemini's semantic understanding"""
        try:
            ranked_docs = []
            for doc in documents:
                content = doc.get('content', '')
                title = doc.get('title', '')
                
                # Create a prompt for Gemini to evaluate relevance
                prompt = f"""Analyze the semantic relevance between this search query and document:

                Query: "{query}"

                Document Title: {title}
                Document Content: {content[:1000]}  # Limit content length

                Tasks:
                1. Evaluate how well the document answers the query
                2. Consider semantic meaning, not just keyword matches
                3. Check information relevance and quality
                4. Account for content freshness and authority

                Output a single number between 0 and 1 where:
                - 1.0: Perfectly relevant, directly answers the query
                - 0.8-0.9: Highly relevant, provides good information
                - 0.5-0.7: Moderately relevant, contains some useful information
                - 0.1-0.4: Slightly relevant, mentions related topics
                - 0.0: Not relevant at all

                Format response as a single decimal number (e.g., 0.85)"""

                try:
                    response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.model.generate_content(prompt)
                    )
                    
                    # Extract the relevance score
                    score = float(response.text.strip())
                    # Ensure score is between 0 and 1
                    score = max(0.0, min(1.0, score))
                    
                except Exception as e:
                    logger.warning(f"Error getting Gemini relevance score: {str(e)}")
                    # Fallback to basic relevance
                    score = 0.5
                    
                doc['relevance'] = score
                ranked_docs.append(doc)

                # Add small delay between requests
                await asyncio.sleep(0.1)
            
            # Sort by relevance score
            ranked_docs.sort(key=lambda x: x['relevance'], reverse=True)
            return ranked_docs

        except Exception as e:
            logger.error(f"Error ranking documents: {str(e)}")
            return documents

    async def summarize_content(self, documents: List[Dict[str, str]], query: str) -> Dict[str, any]:
        """Generate a comprehensive summary from documents and return all relevant documents"""
        try:
            # Sort documents by relevance
            all_ranked_docs = sorted(documents, key=lambda x: x.get('relevance', 0), reverse=True)
            
            # Filter documents with relevance score >= 0.8 (80% or higher relevance)
            high_relevance_docs = [doc for doc in documents if doc.get('relevance', 0) >= 0.8]
            
            # Get the top documents for summary generation (either high relevance or top 3)
            summary_docs = high_relevance_docs if high_relevance_docs else all_ranked_docs[:3]
            
            if not summary_docs:
                return {
                    "summary": "No relevant information found for your query.",
                    "all_docs": all_ranked_docs,
                    "high_relevance_docs": []
                }

            # Combine content from documents to summarize
            combined_content = "\n\n".join([
                f"Title: {doc.get('title', 'No title')}\n"
                f"Content: {doc.get('snippet', 'No content')}\n"
                f"Relevance: {doc.get('relevance', 0):.2%}"
                for doc in summary_docs
            ])

            # Create a prompt for Gemini to generate comprehensive summary
            prompt = f"""Generate a comprehensive summary of these documents for the query: "{query}"

            Documents:
            {combined_content[:4000]}  # Limit content length for Gemini

            Requirements:
            1. Focus on answering the query directly and accurately
            2. Synthesize information across all provided documents
            3. Include specific facts, figures, and data points when available
            4. Maintain factual accuracy
            5. Use clear, professional language
            6. Organize information logically
            7. If documents have varying relevance scores, prioritize information from higher-scoring documents
            8. For specific queries (e.g., "What is the price of X?"), provide a direct answer
            9. For broader queries, provide a well-structured overview
            10. If information seems outdated or uncertain, note that in the summary
            11. Example query: "Ram Chandra Oli Kathmadu University" -> Only provide information about this specific person

            Format the summary in clear, readable paragraphs with appropriate spacing."""

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            
            summary = response.text.strip()
            
            # Clean up the summary
            if not summary:
                summary = "Unable to generate summary. Please try refining your search query."
            
            summary = re.sub(r'\n{3,}', '\n\n', summary)  # Remove excessive newlines
            summary = re.sub(r'\s+', ' ', summary)  # Normalize whitespace
            
            return {
                "summary": summary,
                "all_docs": all_ranked_docs,
                "high_relevance_docs": high_relevance_docs
            }

        except Exception as e:
            logger.error(f"Error generating comprehensive summary: {str(e)}")
            # Return a basic summary with available information
            try:
                all_content = " ".join([doc.get('snippet', '') for doc in documents[:3]])
                basic_summary = f"Based on the available information: {all_content[:500]}..."
                return {
                    "summary": basic_summary,
                    "all_docs": documents,
                    "high_relevance_docs": high_relevance_docs if 'high_relevance_docs' in locals() else []
                }
            except:
                return {
                    "summary": "An error occurred while generating the summary. Please try again.",
                    "all_docs": documents,
                    "high_relevance_docs": []
                }

    async def translate_to_nepali(self, text: str) -> str:
        """Translate text to Nepali using Gemini"""
        try:
            prompt = f"""Translate the following English text to Nepali. 
            Keep the formatting and maintain professional language.
            If there are technical terms, provide appropriate Nepali translations or keep them in English if necessary.
            
            Text to translate:
            {text}
            
            Requirements:
            1. Maintain the original meaning and context
            2. Keep numbers, dates, and technical terms accurate
            3. Use proper Nepali grammar and script
            4. Keep the same paragraph structure
            5. If certain technical terms are better understood in English, keep them in English
            
            Provide the Nepali translation only, without any explanations."""

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            
            translated_text = response.text.strip()
            return translated_text if translated_text else text

        except Exception as e:
            logger.error(f"Error translating to Nepali: {str(e)}")
            return text  # Return original text if translation fails

    async def translate_from_nepali(self, text: str) -> str:
        """Translate text from Nepali to English using Gemini"""
        try:
            prompt = f"""Translate the following Nepali text to English. 
            Keep the formatting and maintain professional language.
            If there are technical terms, provide appropriate English translations.
            
            Text to translate:
            {text}
            
            Requirements:
            1. Maintain the original meaning and context
            2. Keep numbers and technical terms accurate
            3. Use proper English grammar
            4. Keep the same paragraph structure
            5. For technical terms, use standard English terminology
            
            Provide the English translation only, without any explanations."""

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.model.generate_content(prompt)
            )
            
            translated_text = response.text.strip()
            return translated_text if translated_text else text

        except Exception as e:
            logger.error(f"Error translating from Nepali: {str(e)}")
            return text  # Return original text if translation fails
