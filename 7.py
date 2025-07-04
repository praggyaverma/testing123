import fitz

def extract_chunks_on_font_size_relaxed(pdf_path, font_threshold=9.0, min_font=6.0):
    doc = fitz.open(pdf_path)
    sections = []
    current_text = ""
    section_count = 1

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
                        continue
                    text_line += span["text"]
                    max_font_size = max(max_font_size, size)

                text_line = text_line.strip()
                if not text_line:
                    continue

                # Treat any larger font paragraph as a boundary
                if max_font_size > font_threshold:
                    if current_text.strip():
                        sections.append((f"Section {section_count}", current_text.strip()))
                        section_count += 1
                        current_text = ""
                current_text += text_line + "\n"

    # Final section
    if current_text.strip():
        sections.append((f"Section {section_count}", current_text.strip()))

    return sections

# 🧪 Try it
pdf_path = "your_pdf.pdf"
chunks = extract_chunks_on_font_size_relaxed(pdf_path)

for heading, content in chunks:
    print(f"\n🔸 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
