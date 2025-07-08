import pdfplumber

def extract_infobox_tables_text(pdf_path):
    all_data = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"\n📄 Page {i + 1}")
            page_output = {
                "page": i + 1,
                "text": "",
                "tables": [],
                "infobox": None
            }

            width, height = page.width, page.height

            table_objects = page.find_tables()
            table_bboxes = [t.bbox for t in table_objects]

            # Separate potential infobox
            infobox_detected = False
            for idx, table in enumerate(table_objects):
                x0, top, x1, bottom = table.bbox
                bbox_width = x1 - x0
                bbox_height = bottom - top

                # Heuristic: Top-right box, not too tall or wide
                if (
                    x0 > width * 0.55 and       # right side
                    top < height * 0.3 and      # near top
                    bbox_height < height * 0.5  # not too tall
                ):
                    print("📌 Detected potential infobox")
                    table_data = table.extract()
                    infobox_str = "\n".join([" | ".join([cell or "" for cell in row]) for row in table_data])
                    page_output["infobox"] = infobox_str
                    infobox_detected = True
                    del table_objects[idx]  # remove from general table list
                    break  # assume only one infobox per page

            # Extract remaining tables
            for table in table_objects:
                table_data = table.extract()
                table_str = "\n".join([" | ".join([cell or "" for cell in row]) for row in table_data])
                page_output["tables"].append(table_str)

            # Mask table + infobox zones for clean text
            bboxes_to_mask = [t.bbox for t in table_objects]
            if infobox_detected:
                bboxes_to_mask.append((x0, top, x1, bottom))  # infobox bbox

            clean_text_parts = []
            for bbox in bboxes_to_mask:
                top_box = (0, 0, width, bbox[1])
                bottom_box = (0, bbox[3], width, height)
                top_text = page.within_bbox(top_box).extract_text() or ""
                bottom_text = page.within_bbox(bottom_box).extract_text() or ""
                clean_text_parts.append(top_text)
                clean_text_parts.append(bottom_text)

            full_clean_text = "\n".join(clean_text_parts).strip()
            if not bboxes_to_mask:
                full_clean_text = page.extract_text() or ""

            page_output["text"] = full_clean_text
            all_data.append(page_output)

    return all_data
