import fitz

def extract_smart_chunks(pdf_path, heading_font_min=10.0, min_font=6.0, max_words=500):
    doc = fitz.open(pdf_path)
    sections = []
    lines_buffer = []
    section_text = ""
    section_heading = "Introduction"
    section_count = 1

    def split_into_chunks(title, text, max_words):
        words = text.split()
        chunks = []
        for i in range(0, len(words), max_words):
            chunk_words = words[i:i + max_words]
            chunk = " ".join(chunk_words)
            chunk_title = title if i == 0 else f"{title} (cont. {i // max_words + 1})"
            chunks.append((chunk_title, chunk))
        return chunks

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            spans = []
            for line in block["lines"]:
                text_line = ""
                max_font_size = 0.0
                for span in line["spans"]:
                    if span["size"] < min_font:
                        continue
                    text_line += span["text"]
                    max_font_size = max(max_font_size, span["size"])
                text_line = text_line.strip()
                if text_line:
                    spans.append((text_line, max_font_size))

            lines_buffer.extend(spans)

    i = 0
    while i < len(lines_buffer):
        text_line, font_size = lines_buffer[i]

        # Look ahead to the next 1-2 lines
        next_sizes = [lines_buffer[j][1] for j in range(i+1, min(i+3, len(lines_buffer)))]
        if font_size >= heading_font_min and all(font_size > ns for ns in next_sizes):
            # Save current section
            if section_text.strip():
                chunks = split_into_chunks(section_heading, section_text.strip(), max_words)
                sections.extend(chunks)
                section_text = ""

            section_heading = text_line
            section_count += 1
        else:
            section_text += text_line + "\n"

        i += 1

    if section_text.strip():
        chunks = split_into_chunks(section_heading, section_text.strip(), max_words)
        sections.extend(chunks)

    return sections

# 🧪 Try it
pdf_path = "your_pdf.pdf"
chunks = extract_smart_chunks(pdf_path)

for heading, content in chunks:
    print(f"\n🔹 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
