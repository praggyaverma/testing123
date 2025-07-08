import camelot

def extract_infobox(pdf_path, page="1", x_min=300, y_min=400):
    infobox = None

    try:
        tables = camelot.read_pdf(
            pdf_path,
            pages=page,
            flavor="stream",
            strip_text="\n"
        )
    except Exception as e:
        print(f"❌ Camelot error: {e}")
        return None

    for table in tables:
        x1, y1, x2, y2 = table._bbox

        # Heuristic location filter: right-hand side + near top
        if x1 >= x_min and y2 >= y_min:
            df = table.df

            # Heuristic: 2-column table with short keys
            if df.shape[1] == 2 and df.shape[0] >= 4:
                avg_key_len = df[0].str.len().mean()
                if avg_key_len < 40:  # likely key-value pairs
                    print(f"✅ Found infobox candidate: bbox={table._bbox}")
                    infobox = dict(zip(df[0], df[1]))
                    break  # Take first match

    return infobox
infobox = extract_infobox("your_file.pdf")

if infobox:
    print("📌 INFOBOX:")
    for key, value in infobox.items():
        print(f"{key.strip()}: {value.strip()}")
else:
    print("⚠️ No infobox found")
tables.export("debug_output", f="pdf", compress=False)
