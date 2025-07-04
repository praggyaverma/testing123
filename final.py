import fitz

def extract_and_split_chunks(pdf_path, font_threshold=9.0, min_font=6.0, max_words=500):
    doc = fitz.open(pdf_path)
    sections = []
    current_heading = None
    current_text = ""

    def split_into_word_chunks(heading, text, max_words=500):
        words = text.split()
        chunks = []
        for i in range(0, len(words), max_words):
            chunk_words = words[i:i + max_words]
            chunk_text = " ".join(chunk_words)
            chunk_heading = heading if i == 0 else f"{heading} (cont. {i // max_words + 1})"
            chunks.append((chunk_heading, chunk_text))
        return chunks

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

                if max_font_size > font_threshold:
                    # Save previous section
                    if current_text.strip() and current_heading:
                        split_chunks = split_into_word_chunks(current_heading, current_text.strip(), max_words)
                        sections.extend(split_chunks)
                    current_heading = text_line
                    current_text = ""
                else:
                    current_text += text_line + "\n"

    # Final chunk
    if current_text.strip() and current_heading:
        split_chunks = split_into_word_chunks(current_heading, current_text.strip(), max_words)
        sections.extend(split_chunks)

    return sections

# 📂 Try it
pdf_path = "your_pdf.pdf"
chunks = extract_and_split_chunks(pdf_path)

for heading, content in chunks:
    print(f"\n🔸 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
