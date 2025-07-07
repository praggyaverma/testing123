import os
from typing import Dict, List, Any, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import PyPDF2
from io import BytesIO
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """State for the PDF processing agent"""
    pdf_path: str
    current_page: int
    total_pages: int
    documents: List[Dict[str, str]]
    raw_pages: List[str]
    error: str
    finished: bool

class PDFProcessingAgent:
    def __init__(self, azure_endpoint: str, api_key: str, api_version: str = "2024-02-15-preview"):
        """
        Initialize the PDF processing agent
        
        Args:
            azure_endpoint: Azure OpenAI endpoint
            api_key: Azure OpenAI API key
            api_version: API version
        """
        self.llm = ChatOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version,
            model="gpt-4",  # or your preferred model
            temperature=0.3
        )
        
        # Create the prompt template for heading generation
        self.heading_prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are an expert document analyzer. Your task is to analyze the given text content and generate an appropriate heading that summarizes the main topic or section.

Rules:
1. Generate a concise, descriptive heading (max 10 words)
2. The heading should capture the main theme or topic of the content
3. Use title case formatting
4. If the content appears to be a continuation of a previous section, make the heading reflect that
5. If the content is mostly whitespace or minimal text, use "Miscellaneous Content" as the heading

Return only the heading text, nothing else."""),
            HumanMessage(content="Text content to analyze:\n\n{content}")
        ])
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("load_pdf", self._load_pdf)
        workflow.add_node("extract_page", self._extract_page)
        workflow.add_node("generate_heading", self._generate_heading)
        workflow.add_node("check_completion", self._check_completion)
        
        # Add edges
        workflow.set_entry_point("load_pdf")
        workflow.add_edge("load_pdf", "extract_page")
        workflow.add_edge("extract_page", "generate_heading")
        workflow.add_edge("generate_heading", "check_completion")
        
        # Conditional edge from check_completion
        workflow.add_conditional_edges(
            "check_completion",
            self._should_continue,
            {
                "continue": "extract_page",
                "end": END
            }
        )
        
        return workflow.compile()
    
    def _load_pdf(self, state: AgentState) -> AgentState:
        """Load PDF and initialize state"""
        try:
            logger.info(f"Loading PDF: {state['pdf_path']}")
            
            with open(state['pdf_path'], 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                # Extract all pages text
                raw_pages = []
                for page_num in range(total_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    raw_pages.append(text)
                
                state.update({
                    'total_pages': total_pages,
                    'raw_pages': raw_pages,
                    'current_page': 0,
                    'documents': [],
                    'error': '',
                    'finished': False
                })
                
                logger.info(f"PDF loaded successfully. Total pages: {total_pages}")
                
        except Exception as e:
            logger.error(f"Error loading PDF: {str(e)}")
            state['error'] = f"Error loading PDF: {str(e)}"
            state['finished'] = True
        
        return state
    
    def _extract_page(self, state: AgentState) -> AgentState:
        """Extract content from current page"""
        try:
            if state['current_page'] >= state['total_pages']:
                state['finished'] = True
                return state
            
            current_page = state['current_page']
            logger.info(f"Extracting page {current_page + 1}/{state['total_pages']}")
            
            # The raw content is already extracted, just pass it along
            # This step could be enhanced with additional processing if needed
            
        except Exception as e:
            logger.error(f"Error extracting page {state['current_page']}: {str(e)}")
            state['error'] = f"Error extracting page: {str(e)}"
        
        return state
    
    def _generate_heading(self, state: AgentState) -> AgentState:
        """Generate heading for current page content using LLM"""
        try:
            current_page = state['current_page']
            raw_content = state['raw_pages'][current_page]
            
            logger.info(f"Generating heading for page {current_page + 1}")
            
            # Skip if content is too short or empty
            if len(raw_content.strip()) < 10:
                heading = "Miscellaneous Content"
                logger.info(f"Content too short, using default heading: {heading}")
            else:
                # Use LLM to generate heading
                messages = self.heading_prompt.format_messages(content=raw_content)
                response = self.llm.invoke(messages)
                heading = response.content.strip()
                
                # Fallback if LLM returns empty response
                if not heading:
                    heading = f"Page {current_page + 1} Content"
            
            # Create document entry
            document = {
                "heading": heading,
                "raw_content": raw_content,
                "page_number": current_page + 1
            }
            
            state['documents'].append(document)
            logger.info(f"Generated heading: '{heading}' for page {current_page + 1}")
            
        except Exception as e:
            logger.error(f"Error generating heading for page {state['current_page']}: {str(e)}")
            # Continue with default heading on error
            document = {
                "heading": f"Page {state['current_page'] + 1} Content",
                "raw_content": state['raw_pages'][state['current_page']],
                "page_number": state['current_page'] + 1
            }
            state['documents'].append(document)
        
        return state
    
    def _check_completion(self, state: AgentState) -> AgentState:
        """Check if processing is complete"""
        state['current_page'] += 1
        
        if state['current_page'] >= state['total_pages']:
            state['finished'] = True
            logger.info("PDF processing completed successfully")
        
        return state
    
    def _should_continue(self, state: AgentState) -> str:
        """Determine if processing should continue"""
        if state['finished'] or state['error']:
            return "end"
        return "continue"
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Process a PDF file and return structured documents
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing processed documents and metadata
        """
        initial_state = AgentState(
            pdf_path=pdf_path,
            current_page=0,
            total_pages=0,
            documents=[],
            raw_pages=[],
            error='',
            finished=False
        )
        
        # Run the graph
        final_state = self.graph.invoke(initial_state)
        
        # Return results
        return {
            'success': not bool(final_state['error']),
            'error': final_state['error'],
            'total_pages': final_state['total_pages'],
            'documents': final_state['documents'],
            'summary': {
                'total_pages_processed': len(final_state['documents']),
                'headings_generated': [doc['heading'] for doc in final_state['documents']]
            }
        }

# Example usage
def main():
    """Example usage of the PDF processing agent"""
    
    # Configuration - replace with your Azure OpenAI credentials
    AZURE_ENDPOINT = "https://your-resource-name.openai.azure.com/"
    API_KEY = "your-api-key-here"
    API_VERSION = "2024-02-15-preview"
    
    # Initialize the agent
    agent = PDFProcessingAgent(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY,
        api_version=API_VERSION
    )
    
    # Process a PDF file
    pdf_path = "path/to/your/document.pdf"
    
    try:
        result = agent.process_pdf(pdf_path)
        
        if result['success']:
            print(f"Successfully processed {result['total_pages']} pages")
            print(f"Generated {len(result['documents'])} documents")
            
            # Print results
            for i, doc in enumerate(result['documents'], 1):
                print(f"\n--- Document {i} ---")
                print(f"Page: {doc['page_number']}")
                print(f"Heading: {doc['heading']}")
                print(f"Content preview: {doc['raw_content'][:200]}...")
                
        else:
            print(f"Error processing PDF: {result['error']}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
