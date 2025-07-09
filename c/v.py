from collections import defaultdict

# Suppose `docs` is your list of parsed Document objects
grouped_chunks = defaultdict(list)

for doc in docs:
    metadata = doc.metadata
    parent_id = metadata.get("parent_id") or metadata.get("element_id")  # Use own ID if no parent
    grouped_chunks[parent_id].append(doc)

# Sort each group by Y position on the page (descending = top-to-bottom)
def get_y_start(doc):
    coords = doc.metadata.get("coordinates", {}).get("points")
    if coords:
        return coords[0][1]  # Y value of first point
    return float("inf")  # fallback for sorting

for key, chunk in grouped_chunks.items():
    chunk.sort(key=get_y_start)

# Convert to plain text chunks
final_chunks = []
for section_docs in grouped_chunks.values():
    combined_text = "\n".join([d.page_content for d in section_docs])
    final_chunks.append(combined_text)

# Show result
for i, chunk in enumerate(final_chunks[:5]):  # preview first 5
    print(f"--- Chunk {i+1} ---")
    print(chunk[:500], "\n")
