import camelot
import pdfplumber

def extract_text_excluding_tables(pdf_path, x_min=300, x_max=600):
    result = []

    # Step 1: Use Camelot to find tables within x_min to x_max
    camelot_tables = camelot.read_pdf(
        pdf_path,
        flavor="stream",
        pages="all",
        strip_text="\n"
    )

    # Store table info with bounding boxes
    tables_by_page = {}

    for table in camelot_tables:
        page_num = table.page
        x1, y1, x2, y2 = table._bbox  # Camelot uses (x1, y1, x2, y2)
        if x1 >= x_min and x2 <= x_max:
            tables_by_page.setdefault(page_num, []).append({
                "bbox": (x1, y1, x2, y2),
                "data": table.df
            })

    # Step 2: Use pdfplumber and mask table regions
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_number = i + 1
            page_result = {
                "page": page_number,
                "text": "",
                "tables": []
            }

            page_width = page.width
            page_height = page.height

            # Get all table bounding boxes on this page
            table_regions = tables_by_page.get(str(page_number), [])

            # Mask each table region: extract text outside them
            if table_regions:
                text_parts = []

                for region in table_regions:
                    bbox = region["bbox"]
                    page_result["tables"].append({
                        "bbox": bbox,
                        "data": region["data"]
                    })

                    # Get top and bottom regions (above and below the table)
                    top = (0, bbox[3], page_width, page_height)  # y2 to top
                    bottom = (0, 0, page_width, bbox[1])         # bottom to y1

                    top_text = page.within_bbox(top).extract_text() or ""
                    bottom_text = page.within_bbox(bottom).extract_text() or ""

                    text_parts.append(top_text.strip())
                    text_parts.append(bottom_text.strip())

                page_result["text"] = "\n".join(text_parts).strip()
            else:
                # No table on this page, extract full text
                page_result["text"] = page.extract_text() or ""

            result.append(page_result)

    return result
