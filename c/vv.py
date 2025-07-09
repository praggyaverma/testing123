from collections import defaultdict

# Input: list of parsed Document objects (already in correct order)
grouped_chunks = defaultdict(list)

for doc in docs:
    metadata = doc.metadata
    parent_id = metadata.get("parent_id") or metadata.get("element_id")
    grouped_chunks[parent_id].append(doc)

# Build final chunks by combining text (in order, no sorting!)
final_chunks = []
for section_docs in grouped_chunks.values():
    title = ""
    body_texts = []

    for d in section_docs:
        if d.metadata.get("category") == "Title" and not title:
            title = d.page_content
        else:
            body_texts.append(d.page_content)

    chunk = f"{title}\n\n" + "\n".join(body_texts) if title else "\n".join(body_texts)
    final_chunks.append(chunk)

# Preview a few chunks
for i, chunk in enumerate(final_chunks[:3]):
    print(f"--- Chunk {i+1} ---")
    print(chunk[:500], "\n")
