import streamlit as st
import asyncio
from search_engine import SearchEngine
from web_scraper import WebScraper
from semantic_processor import SemanticProcessor
import logging
from typing import List, Dict
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SemanticSearchApp:
    def __init__(self):
        self.search_engine = SearchEngine()
        self.web_scraper = WebScraper()
        self.semantic_processor = SemanticProcessor()

    async def translate_content(self, content: Dict[str, any]) -> Dict[str, any]:
        """Translate content to Nepali"""
        try:
            # Translate summary
            if content.get('summary'):
                content['summary'] = await self.semantic_processor.translate_to_nepali(content['summary'])
            
            # Translate high relevance docs
            for doc in content.get('high_relevance_docs', []):
                if doc.get('title'):
                    doc['title'] = await self.semantic_processor.translate_to_nepali(doc['title'])
                if doc.get('snippet'):
                    doc['snippet'] = await self.semantic_processor.translate_to_nepali(doc['snippet'])
            
            # Translate other docs
            for doc in content.get('all_docs', []):
                if doc not in content.get('high_relevance_docs', []):
                    if doc.get('title'):
                        doc['title'] = await self.semantic_processor.translate_to_nepali(doc['title'])
                    if doc.get('snippet'):
                        doc['snippet'] = await self.semantic_processor.translate_to_nepali(doc['snippet'])
            
            return content
        except Exception as e:
            logger.error(f"Error translating content: {str(e)}")
            return content

    async def process_query(self, query: str) -> Dict[str, any]:
        try:
            # If language is Nepali, translate query to English first
            original_query = query
            if st.session_state.language == 'ne':
                query = await self.semantic_processor.translate_from_nepali(query)
                status_text = "🔍 खोज्दै..." if st.session_state.language == 'ne' else "🔍 Searching..."
                not_found_text = "कुनै नतिजा फेला परेन" if st.session_state.language == 'ne' else "No results found"
                results_found_text = "नतिजाहरू फेला परे" if st.session_state.language == 'ne' else "results found"
            else:
                status_text = "🔍 Searching..."
                not_found_text = "No results found"
                results_found_text = "results found"

            with st.status(status_text) as status:
                # Search and rank documents
                search_results = await self.search_engine.search(query, max_results=10)
                if not search_results:
                    status.update(label=not_found_text, state="error")
                    return None
                status.update(label=f"{len(search_results)} {results_found_text}!", state="complete")
            
            # Generate comprehensive summary
            results = await self.semantic_processor.summarize_content(search_results, query)
            
            # Translate content if language is Nepali
            if st.session_state.language == 'ne':
                results = await self.translate_content(results)
            
            return results

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            error_msg = "तपाईंको खोज प्रक्रिया गर्दा त्रुटि भयो" if st.session_state.language == 'ne' else "An error occurred while processing your query"
            st.error(f"{error_msg}: {str(e)}")
            return None



def main():
    st.set_page_config(
        page_title="Semantic Search Engine",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Initialize session state for language
    if 'language' not in st.session_state:
        st.session_state.language = 'en'

    # Custom CSS for better UI and language toggle
    st.markdown("""
    <style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        height: 3rem;
        background-color: #1E4134;
        color: white;
        font-size: 1.1rem;
        margin-top: 1rem;
    }
    .language-toggle {
        position: fixed;
        top: 1rem;
        right: 1rem;
        z-index: 1000;
        background-color: #1A1C24;
        padding: 0.5rem;
        border-radius: 10px;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .stProgress > div > div > div {
        background-color: #1E4134;
    }
    .stExpander {
        background-color: #1A1C24;
        border-radius: 10px;
        margin-bottom: 0.5rem;
    }
    .search-container {
        background-color: #1A1C24;
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
    }
    .summary-container {
        background-color: #1E4134;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        color: white;
    }
    .sources-header {
        color: #A0AEC0;
        margin: 2rem 0 1rem 0;
        font-size: 1.2rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # Language toggle in the corner
    with st.container():
        st.markdown(
            """
            <div class='language-toggle'>
                <span style='color: white;'>🌐</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        col1, col2 = st.columns([10, 2])
        with col2:
            if st.toggle("नेपाली", value=st.session_state.language == 'ne'):
                st.session_state.language = 'ne'
            else:
                st.session_state.language = 'en'

    # Conditional title and description based on language
    title = "🔍 खोज इन्जिन" if st.session_state.language == 'ne' else "🔍 Semantic Search Engine"
    description = "एआई-सक्षम सिमेन्टिक खोजको साथ सान्दर्भिक जानकारी पत्ता लगाउनुहोस्" if st.session_state.language == 'ne' else "Discover relevant information with AI-powered semantic search"
    
    st.markdown(f"""
        <h1 style='text-align: center; color: #FAFAFA; margin-bottom: 2rem;'>
            {title}
        </h1>
        <p style='text-align: center; color: #A0AEC0; font-size: 1.2rem; margin-bottom: 3rem;'>
            {description}
        </p>
    """, unsafe_allow_html=True)

    if 'app' not in st.session_state:
        st.session_state.app = SemanticSearchApp()

    st.markdown('<div class="search-container">', unsafe_allow_html=True)
    placeholder = "उदाहरण: स्वास्थ्य सेवामा एआई विकास" if st.session_state.language == 'ne' else "e.g., Latest AI developments in healthcare"
    query = st.text_input(
        "तपाईंको खोज प्रश्न लेख्नुहोस्" if st.session_state.language == 'ne' else "Enter your search query",
        placeholder=placeholder,
        key="search_input"
    )
    search_button_text = "🔍 खोज्नुहोस्" if st.session_state.language == 'ne' else "🔍 Search"
    search_clicked = st.button(search_button_text, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if search_clicked and query:
        results = asyncio.run(st.session_state.app.process_query(query))
        
        if results:
            # Display headers in selected language
            summary_header = "📑 विस्तृत सारांश" if st.session_state.language == 'ne' else "📑 Comprehensive Summary"
            high_rel_header = "🎯 अति सान्दर्भिक कागजातहरू" if st.session_state.language == 'ne' else "🎯 Highly Relevant Documents"
            other_docs_header = "📚 अन्य सम्बन्धित कागजातहरू" if st.session_state.language == 'ne' else "📚 Other Related Documents"

            # Display the comprehensive summary
            st.markdown(f"### {summary_header}")
            
            summary = results.get('summary', 'Summary not available.' if st.session_state.language == 'en' else 'सारांश उपलब्ध छैन।')
            
            st.markdown(
                f"""<div class="summary-container">
                    {summary}
                </div>""",
                unsafe_allow_html=True
            )
            
            # Display highly relevant documents
            high_relevance_docs = results.get('high_relevance_docs', [])
            if high_relevance_docs:
                st.markdown(f"### {high_rel_header} ({len(high_relevance_docs)})")
                for doc in high_relevance_docs:
                    st.markdown(f"""
                    <div style='background-color: #1A1C24; padding: 1rem; border-radius: 10px; margin-bottom: 0.5rem;'>
                        <h4 style='margin: 0;'>{doc.get('title', 'No title')}</h4>
                        <p style='color: #00FF00; margin: 0.5rem 0;'>Relevance: {doc.get('relevance', 0):.0%}</p>
                        <p>{doc.get('snippet', 'No content available')}</p>
                        <a href="{doc.get('url', '#')}" target="_blank">Read more →</a>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Display other relevant documents
            all_docs = results.get('all_docs', [])
            other_docs = [d for d in all_docs if d not in high_relevance_docs]
            if other_docs:
                st.markdown(f"### {other_docs_header} ({len(other_docs)})")
                for doc in other_docs:
                    st.markdown(f"""
                    <div style='background-color: #1A1C24; padding: 1rem; border-radius: 10px; margin-bottom: 0.5rem; opacity: 0.8;'>
                        <h4 style='margin: 0;'>{doc.get('title', 'No title')}</h4>
                        <p style='color: #FFA500; margin: 0.5rem 0;'>Relevance: {doc.get('relevance', 0):.0%}</p>
                        <p>{doc.get('snippet', 'No content available')}</p>
                        <a href="{doc.get('url', '#')}" target="_blank">Read more →</a>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.warning("No results found. Please try a different query.")

if __name__ == "__main__":
    main()
