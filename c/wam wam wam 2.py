import camelot
import pdfplumber
import fitz  # PyMuPDF
import os
from typing import List, Tuple, Dict

def process_pdf(pdf_path: str) -> Tuple[List[str], List[str], List[Dict]]:
    # Step 1: Extract tables using Camelot
    tables = camelot.read_pdf(pdf_path, flavor='lattice', strip_text='\n',
                              table_areas=['300,800,600,0'], pages='all')
    
    table_info = []
    for table in tables:
        bbox = table._bbox  # (x1, y1, x2, y2)
        table_info.append({
            'page': table.page,
            'bbox': bbox,
            'data': table.df
        })
    
    # Step 2: Mask table areas in the original PDF using PyMuPDF (fitz)
    doc = fitz.open(pdf_path)
    for info in table_info:
        page_num = int(info['page']) - 1
        bbox = info['bbox']
        # bbox = (x1, y1, x2, y2)
        rect = fitz.Rect(bbox[0], bbox[3], bbox[2], bbox[1])  # fitz uses (x0, y0, x1, y1)
        page = doc[page_num]
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))  # white mask

    modified_pdf_path = os.path.splitext(pdf_path)[0] + "_masked.pdf"
    doc.save(modified_pdf_path)
    doc.close()

    # Step 3: Extract text using pdfplumber
    pages_text = []
    full_text = []

    with pdfplumber.open(modified_pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            pages_text.append(text if text else "")
            full_text.append(text if text else "")
    
    return pages_text, full_text, table_info
