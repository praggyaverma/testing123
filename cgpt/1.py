import fitz
from bs4 import BeautifulSoup

def parse_pdf_with_html(pdf_path, heading_font_threshold=11):
    doc = fitz.open(pdf_path)
    sections = []
    current_heading = "Introduction"
    current_text = ""

    for page in doc:
        html = page.get_text("html")
        soup = BeautifulSoup(html, "html.parser")

        for span in soup.find_all("span"):
            style = span.get("style", "")
            text = span.get_text().strip()
            if not text:
                continue

            # Extract font size from style string
            font_size = None
            if "font:" in style:
                try:
                    font_part = style.split("font:")[1].split("px")[0]
                    font_size = float(font_part)
                except:
                    pass

            if font_size is not None:
                if font_size > heading_font_threshold:
                    # Save current section before starting new one
                    if current_text.strip():
                        sections.append((current_heading, current_text.strip()))
                    current_heading = text
                    current_text = ""
                else:
                    current_text += text + " "

    # Final section
    if current_text.strip():
        sections.append((current_heading, current_text.strip()))

    return sections

# 🧪 Try it
pdf_path = "your_pdf.pdf"
chunks = parse_pdf_with_html(pdf_path)

for heading, content in chunks:
    print(f"\n🔹 {heading}\n{'-' * 50}")
    print(content[:500], "...\n")
