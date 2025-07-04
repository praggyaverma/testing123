import fitz  # PyMuPDF

def extract_topic_chunks(pdf_path):
    doc = fitz.open(pdf_path)
    sections = []
    current_heading = "Introduction"
    current_text = ""

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text_line = ""
                max_font_size = 0
                for span in line["spans"]:
                    text_line += span["text"]
                    max_font_size = max(max_font_size, span["size"])

                # Heuristic: Treat large font size as heading
                if max_font_size >= 13 and len(text_line.strip()) > 0:
                    if current_text.strip():
                        sections.append((current_heading, current_text.strip()))
                    current_heading = text_line.strip()
                    current_text = ""
                else:
                    current_text += text_line + "\n"

    if current_text.strip():
        sections.append((current_heading, current_text.strip()))

    return sections

# Usage
pdf_path = "your_pdf.pdf"  # Replace with your PDF path
chunks = extract_topic_chunks(pdf_path)

# Print extracted topic chunks
for heading, content in chunks:
    print(f"\n🔹 Topic: {heading}\n{'-' * 50}")
    print(content[:500], "...")  # Preview only
