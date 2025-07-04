import fitz  # PyMuPDF

def extract_chunks_on_font_size(pdf_path, font_threshold=9.0, min_font=6.0):
    doc = fitz.open(pdf_path)
    sections = []
    current_heading = "Start"
    current_text = ""

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text_line = ""
                max_font_size = 0.0

                for span in line["spans"]:
                    size = span["size"]
                    if size < min_font:
                        continue  # skip tiny noise text
                    text_line += span["text"]
                    max_font_size = max(max_font_size, size)

                text_line = text_line.strip()
                if not text_line:
                    continue

                # If font size > threshold, start new chunk
                if max_font_size > font_threshold:
                    if current_text.strip():
                        sections.append((current_heading, current_text.strip()))
                    current_heading = text_line
                    current_text = ""
                else:
                    current_text += text_line + "\n"

    # Append last chunk
    if current_text.strip():
        sections.append((current_heading, current_text.strip()))

    return sections

# Usage
pdf_path = "your_pdf.pdf"  # Replace with your PDF file
chunks = extract_chunks_on_font_size(pdf_path)

for heading, content in chunks:
    print(f"\n🔹 Chunk Heading: {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
