import pdfplumber

def extract_text_and_tables(file_path):
    output = []

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n📄 Processing Page {i + 1}")
            page_result = {"page": i + 1, "text": "", "tables": []}

            # Detect tables
            tables = page.extract_tables()
            if tables:
                print(f"🔍 Found {len(tables)} table(s)")

                # Save table content
                for table in tables:
                    table_str = "\n".join([" | ".join([cell or "" for cell in row]) for row in table])
                    page_result["tables"].append(table_str)

                # Attempt to isolate table-free text
                # This is an approximation: we assume table region is on right half
                # OR we extract full text anyway if tables aren't overlapping main text

                width = page.width
                height = page.height

                # Crop out the right half (where table often is) — adjust as needed
                left_column = (0, 0, width * 0.65, height)
                left_text = page.within_bbox(left_column).extract_text()

                page_result["text"] = left_text or ""
            else:
                # No tables, extract full text
                text = page.extract_text()
                page_result["text"] = text or ""

            output.append(page_result)

    return output
