import fitz

def inspect_font_sizes(pdf_path):
    doc = fitz.open(pdf_path)
    font_sizes = set()

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    font_sizes.add(round(span["size"], 2))

    print("Unique font sizes in PDF:", sorted(font_sizes, reverse=True))

# Usage
inspect_font_sizes("your_pdf.pdf")


