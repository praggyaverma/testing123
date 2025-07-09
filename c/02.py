import pdfplumber
import re
from collections import defaultdict

def is_heading(text, font_size, threshold=12.0):
    """Heuristic to classify headings based on font size."""
    return font_size >= threshold and len(text.strip()) > 0

def chunk_pdf_topic_wise(pdf_path, heading_font_threshold=12.0):
    topics = defaultdict(list)
    current_topic = "Untitled"
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(extra_attrs=["fontname", "size"])

            for word in words:
                text = word["text"].strip()
                font_size = float(word.get("size", 0))

                if is_heading(text, font_size, threshold=heading_font_threshold):
                    # Set new topic based on detected heading
                    current_topic = f"{text} (p{page_number})"
                    continue

                if text:
                    topics[current_topic].append({
                        "text": text,
                        "page": page_number,
                        "x0": word["x0"],
                        "top": word["top"],
                        "size": font_size
                    })

    # Merge text into chunks
    topic_chunks = {
        topic: " ".join([item["text"] for item in content])
        for topic, content in topics.items()
    }
    
    return topic_chunks

# Example usage
pdf_path = "/content/Audi_A3.pdf"
chunks = chunk_pdf_topic_wise(pdf_path)

# Print or save
for topic, text in chunks.items():
    print(f"\n🟢 Topic: {topic}\n{text[:500]}...\n---")
