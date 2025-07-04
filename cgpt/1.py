import fitz
from bs4 import BeautifulSoup

def parse_pdf_with_html_paragraphs(pdf_path, heading_font_threshold=11, max_words=500):
    doc = fitz.open(pdf_path)
    sections = []
    current_heading = "Introduction"
    current_text = ""

    def split_chunks(heading, text, max_words):
        words = text.split()
        chunks = []
        for i in range(0, len(words), max_words):
            part = " ".join(words[i:i + max_words])
            suffix = f" (cont. {i // max_words + 1})" if i > 0 else ""
            chunks.append((heading + suffix, part))
        return chunks

    for page in doc:
        html = page.get_text("html")
        soup = BeautifulSoup(html, "html.parser")
        paragraphs = soup.find_all("p")

        for para in paragraphs:
            span = para.find("span")
            if not span:
                continue

            text = span.get_text().strip()
            if not text:
                continue

            # Extract font size from style attribute
            font_size = None
            style = span.get("style", "")
            if "font:" in style:
                try:
                    font_part = style.split("font:")[1].split("px")[0]
                    font_size = float(font_part.strip())
                except:
                    continue

            # Heading or body?
            if font_size and font_size > heading_font_threshold:
                # Save the previous section
                if current_text.strip():
                    chunks = split_chunks(current_heading, current_text.strip(), max_words)
                    sections.extend(chunks)
                    current_text = ""
                current_heading = text
            else:
                current_text += text + " "

    # Final section
    if current_text.strip():
        chunks = split_chunks(current_heading, current_text.strip(), max_words)
        sections.extend(chunks)

    return sections

# ✅ Try it
pdf_path = "your_pdf.pdf"
chunks = parse_pdf_with_html_paragraphs(pdf_path)

for heading, content in chunks:
    print(f"\n🔹 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
