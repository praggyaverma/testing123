import fitz

def extract_chunks_smart(pdf_path, font_threshold=9.0, min_font=6.0):
    doc = fitz.open(pdf_path)
    sections = []
    current_text = ""
    section_count = 1

    def is_probable_heading(text, size, flags):
        is_bold = flags & 2 != 0
        is_short = len(text.split()) <= 12
        no_period = not text.endswith(".")
        return size > font_threshold and is_bold and is_short and no_period

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text_line = ""
                max_font_size = 0.0
                bold_flag = 0

                for span in line["spans"]:
                    size = span["size"]
                    if size < min_font:
                        continue
                    text_line += span["text"]
                    max_font_size = max(max_font_size, size)
                    bold_flag = span["flags"]

                text_line = text_line.strip()
                if not text_line:
                    continue

                if is_probable_heading(text_line, max_font_size, bold_flag):
                    if current_text.strip():
                        sections.append((f"Section {section_count}", current_text.strip()))
                        section_count += 1
                    current_text = ""  # Reset content for new section
                else:
                    current_text += text_line + "\n"

    # Final section
    if current_text.strip():
        sections.append((f"Section {section_count}", current_text.strip()))

    return sections

# 🔧 Try it
pdf_path = "your_pdf.pdf"
chunks = extract_chunks_smart(pdf_path)

for heading, content in chunks:
    print(f"\n🔸 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
