def extract_y_position(metadata):
    """Extracts the y-top coordinate from the first point."""
    try:
        return metadata["coordinates"]["points"][0][1]
    except (KeyError, IndexError, TypeError):
        return float("inf")  # fallback for malformed data

# Step 1: Attach Y position for layout tracking
docs_with_y = [
    {"doc": doc, "y": extract_y_position(doc.metadata)}
    for doc in docs
]

# Step 2: Group by visual flow
chunks = []
current_title = None
current_chunk = []

for item in docs_with_y:
    doc = item["doc"]
    category = doc.metadata.get("category", "")
    
    if category == "Title":
        # Save existing chunk before starting a new one
        if current_chunk:
            chunks.append({
                "title": current_title,
                "content": "\n".join(d.page_content for d in current_chunk)
            })
            current_chunk = []

        current_title = doc.page_content.strip()

    elif category == "NarrativeText":
        current_chunk.append(doc)

# Step 3: Append final chunk
if current_chunk:
    chunks.append({
        "title": current_title,
        "content": "\n".join(d.page_content for d in current_chunk)
    })

# Step 4: Format into final text chunks
final_chunks = [
    f"{chunk['title']}\n\n{chunk['content']}".strip()
    for chunk in chunks
]

# Optional preview
for i, chunk in enumerate(final_chunks[:3]):
    print(f"\n--- Chunk {i+1} ---\n{chunk[:500]}...\n")

