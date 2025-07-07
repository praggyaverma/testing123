from langchain.text_splitter import RecursiveCharacterTextSplitter
pip install langchain

def split_pages_into_chunks(pages: List[str], max_words: int = 300) -> List[str]:
    # Convert max_words to approximate characters (average word = ~5 chars + 1 space)
    chunk_size = max_words * 6  # Approx 1800 chars
    chunk_overlap = int(0.1 * chunk_size)  # 10% overlap

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
        length_function=len,
    )

    all_chunks = []
    for page_text in pages:
        chunks = splitter.split_text(page_text)
        all_chunks.extend(chunks)

    return all_chunks


def load_pdf(state: GraphState) -> GraphState:
    path = state["pdf_path"]
    doc = fitz.open(path)
    pages = [page.get_text() for page in doc]

    # Use the splitter here
    chunks = split_pages_into_chunks(pages, max_words=300)

    return {**state, "pages": chunks}  # Replace pages with chunks
