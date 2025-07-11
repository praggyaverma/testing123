import pymupdf
import statistics

import re

def split_into_chunks(title, text, max_words=300):
    words = text.split()
    chunks = []
    i = 0

    while i < len(words):
        end = min(i + max_words, len(words))
        chunk_words = words[i:end]
        chunk_text = " ".join(chunk_words)

        # Try to find nearest sentence boundary or line break before max_words
        match = re.search(r"(?s)^(.+?)(?:(?<=\.)\s+|\n|$)", chunk_text[::-1])  # reverse search
        if match:
            boundary = len(chunk_text) - match.end(1)
            # break at the found sentence boundary
            final_chunk = chunk_text[:len(chunk_text)-boundary].strip()
        else:
            final_chunk = chunk_text.strip()

        # If we can't find anything meaningful, fallback to regular cut
        if not final_chunk:
            final_chunk = " ".join(words[i:end]).strip()
            chunk_len = len(final_chunk.split())
        else:
            chunk_len = len(final_chunk.split())

        chunk_title = title if i == 0 else f"{title} (cont. {len(chunks) + 1})"
        chunks.append((chunk_title, final_chunk))
        i += chunk_len

    return chunks


def is_likely_heading(text, font_size, avg_body_size, next_sizes):
    # Heuristics
    is_bigger = font_size > avg_body_size * 1.1
    is_short = len(text.split()) <= 10
    capital_ratio = sum(1 for w in text.split() if w.istitle() or w.isupper()) / max(1, len(text.split()))
    next_smaller = all(font_size > ns for ns in next_sizes)
    
    return is_bigger and is_short and capital_ratio > 0.5 and next_smaller

def extract_smart_chunks(pdf_path, heading_font_min=10.0, min_font=6.0, max_words=500):
    doc = pymupdf.open(pdf_path)
    sections = []
    lines_buffer = []
    font_sizes = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                text_line = ""
                max_font_size = 0.0
                for span in line["spans"]:
                    if span["size"] < min_font or not span["text"].strip():
                        continue
                    text_line += span["text"]
                    max_font_size = max(max_font_size, span["size"])
                text_line = text_line.strip()
                if text_line:
                    lines_buffer.append((text_line, max_font_size))
                    font_sizes.append(max_font_size)

    # Determine average body text font size
    avg_body_font_size = statistics.median(font_sizes)

    section_heading = "Introduction"
    section_text = ""
    i = 0
    while i < len(lines_buffer):
        text_line, font_size = lines_buffer[i]
        next_sizes = [lines_buffer[j][1] for j in range(i+1, min(i+3, len(lines_buffer)))]

        if is_likely_heading(text_line, font_size, avg_body_font_size, next_sizes):
            if section_text.strip():
                chunks = split_into_chunks(section_heading, section_text.strip(), max_words)
                sections.extend(chunks)
                section_text = ""
            section_heading = text_line
        else:
            section_text += text_line + "\n"
        i += 1

    # Add last section
    if section_text.strip():
        chunks = split_into_chunks(section_heading, section_text.strip(), max_words)
        sections.extend(chunks)

    return sections

# 🧪 Try it
pdf_path = r"/content/Audi_Q3.pdf"
chunks = extract_smart_chunks(pdf_path)

for heading, content in chunks:
    print(f"\n🔹 {heading}\n{'-' * 50}")
    print(content, "\n")
