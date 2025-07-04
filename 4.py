import fitz  # PyMuPDF
from collections import defaultdict

def inspect_fonts_with_text(pdf_path):
    doc = fitz.open(pdf_path)
    font_samples = defaultdict(list)

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 2)
                    text = span["text"].strip()
                    if text:
                        font_samples[size].append(text)

    # Print one example per font size
    for size in sorted(font_samples.keys(), reverse=True):
        sample_text = font_samples[size][0]  # First occurrence
        print(f"🔤 Font size: {size}")
        print(f"   Example: {sample_text[:120]}")
        print("-" * 60)

# 🔧 Use it
pdf_path = "your_pdf.pdf"  # Replace with your actual PDF path
inspect_fonts_with_text(pdf_path)
