from langgraph.graph import StateGraph
from chatazureopenai import ChatAzureOpenAI
from typing import TypedDict, List, Dict
import fitz  # PyMuPDF

# ----- Shared state -----
class GraphState(TypedDict):
    pdf_path: str
    pages: List[str]
    headings: List[str]
    heading_contents: Dict[str, str]

# ----- LangGraph tools -----
llm = ChatAzureOpenAI(deployment_name="gpt-4", temperature=0)

# Step 1: Load PDF and split by page
def load_pdf(state: GraphState) -> GraphState:
    path = state["pdf_path"]
    doc = fitz.open(path)
    pages = [page.get_text() for page in doc]
    return {**state, "pages": pages}

# Step 2: Extract headings using the model
def extract_headings_with_model(state: GraphState) -> GraphState:
    pages = state["pages"]
    prompt = "You are a helpful assistant. Extract all the important section headings from this page's text:\n\n"

    headings = set()
    for page_text in pages:
        messages = [{"role": "user", "content": prompt + page_text}]
        response = llm.invoke(messages)
        # Assume the response is a bullet list of headings
        page_headings = [h.strip("-• \n") for h in response.content.split("\n") if h.strip()]
        headings.update(page_headings)

    return {**state, "headings": list(headings)}

# Step 3: Extract content under each heading
def extract_sections_with_model(state: GraphState) -> GraphState:
    pages = state["pages"]
    headings = state["headings"]
    heading_contents = {}

    for heading in headings:
        collected_text = ""
        for page_text in pages:
            messages = [{
                "role": "user",
                "content": (
                    f"From the following page text, extract the verbatim section related to the heading: '{heading}'. "
                    "Do not rephrase. Return only the original paragraph or section if it exists:\n\n" + page_text)
            }]
            response = llm.invoke(messages)
            if response.content.strip() and heading not in heading_contents:
                collected_text = response.content.strip()
                heading_contents[heading] = collected_text

    return {**state, "heading_contents": heading_contents}

# ----- Build the LangGraph -----
graph_builder = StateGraph(GraphState)
graph_builder.add_node("load_pdf", load_pdf)
graph_builder.add_node("extract_headings", extract_headings_with_model)
graph_builder.add_node("extract_sections", extract_sections_with_model)

graph_builder.set_entry_point("load_pdf")
graph_builder.connect("load_pdf", "extract_headings")
graph_builder.connect("extract_headings", "extract_sections")
graph_builder.set_finish_point("extract_sections")

graph = graph_builder.compile()

# ----- Example usage -----
if __name__ == "__main__":
    result = graph.invoke({"pdf_path": "Audi_A3.pdf"})
    print(result["heading_contents"])
