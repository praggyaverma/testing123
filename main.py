pip install langchain openai pypdf tiktoken sentence-transformers
pip install langchain pypdf sentence-transformers
from langchain.document_loaders import PyPDFLoader

loader = PyPDFLoader("your_file.pdf")
pages = loader.load()
pip install llama-index
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from langchain.docstore.document import Document

# Initialize embedding model
embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")

# Semantic splitter
parser = SemanticSplitterNodeParser(embed_model=embed_model, chunk_size=500)

# Convert LangChain Documents to text
texts = [doc.page_content for doc in pages]

# Parse into semantic chunks (returns LlamaIndex nodes)
nodes = []
for text in texts:
    nodes.extend(parser.get_nodes_from_documents([text]))

# Convert back to LangChain Document
semantic_chunks = [Document(page_content=node.get_content()) for node in nodes]
