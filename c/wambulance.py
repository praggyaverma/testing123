import pdfplumber
import camelot

def extract_from_pdf(pdf_path, infobox_area="350,750,590,500", table_min_rows=3):
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for page_num in range(total_pages):
            page_index = page_num + 1
            print(f"\n📄 Processing Page {page_index}")
            page_result = {
                "page": page_index,
                "text": "",
                "infobox": None,
                "tables": []
            }

            # ---- Step 1: Extract Text with pdfplumber ----
            plumber_page = pdf.pages[page_num]
            full_text = plumber_page.extract_text() or ""
            page_result["text"] = full_text.strip()

            # ---- Step 2: Extract Tables with Camelot ----
            # You can extract full-page tables if needed
            try:
                tables = camelot.read_pdf(
                    pdf_path,
                    pages=str(page_index),
                    flavor="stream",
                    strip_text="\n"
                )
            except Exception as e:
                print(f"⚠️ Camelot error on page {page_index}: {e}")
                continue

            # ---- Step 3: Identify Infobox by Area ----
            try:
                infobox_tables = camelot.read_pdf(
                    pdf_path,
                    pages=str(page_index),
                    flavor="stream",
                    table_areas=[infobox_area],
                    strip_text="\n"
                )
                if infobox_tables:
                    df = infobox_tables[0].df
                    if df.shape[1] == 2 and df.shape[0] >= table_min_rows:
                        avg_len = df[0].apply(lambda x: len(x.strip())).mean()
                        if avg_len < 40:
                            page_result["infobox"] = dict(zip(df[0], df[1]))
            except:
                pass  # It's okay if no infobox found

            # ---- Step 4: Filter Real Tables ----
            for table in tables:
                df = table.df
                if df.shape[1] >= 2 and df.shape[0] >= table_min_rows:
                    # Optional: skip if it's clearly the same as infobox
                    if not page_result["infobox"] or not df.equals(infobox_tables[0].df):
                        page_result["tables"].append(df)

            results.append(page_result)

    return results


data = extract_from_pdf("wikipedia.pdf")

for page in data:
    print(f"\n=== Page {page['page']} ===")
    print(f"📝 TEXT:\n{page['text'][:300]}...\n")
    if page["infobox"]:
        print("📌 INFOBOX:")
        for k, v in page["infobox"].items():
            print(f" - {k.strip()}: {v.strip()}")
    for i, table in enumerate(page["tables"]):
        print(f"\n📊 TABLE {i+1}:\n{table.head()}")
