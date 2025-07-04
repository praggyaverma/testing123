import fitz
import re
from collections import Counter
from typing import List, Tuple, Dict

class WikipediaPDFChunker:
    def __init__(self, 
                 min_font_size: float = 6.0, 
                 max_words_per_chunk: int = 800,
                 min_section_words: int = 100,
                 font_threshold_ratio: float = 1.5):
        self.min_font_size = min_font_size
        self.max_words_per_chunk = max_words_per_chunk
        self.min_section_words = min_section_words
        self.font_threshold_ratio = font_threshold_ratio
        
    def analyze_font_structure(self, doc) -> Dict:
        """Analyze document to find body text and major heading fonts"""
        font_sizes = []
        
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    if line_text.strip() and max_font_size > 0:
                        font_sizes.append(max_font_size)
        
        # Find the most common font size (likely body text)
        font_counter = Counter([round(size, 1) for size in font_sizes])
        body_font = max(font_counter, key=font_counter.get)
        
        # Calculate threshold for major headings
        heading_threshold = body_font * self.font_threshold_ratio
        
        return {
            'body_font': body_font,
            'heading_threshold': heading_threshold,
            'font_distribution': font_counter.most_common(10)
        }
    
    def is_major_heading(self, text: str, font_size: float, font_analysis: Dict) -> bool:
        """Conservative detection of only major section headings"""
        
        # Skip very short or very long text
        if len(text) < 5 or len(text) > 100:
            return False
            
        # Skip if it's just numbers, punctuation, or references
        if re.match(r'^[\d\.\[\]\(\)\s\-–—]+$', text):
            return False
            
        # Skip common non-heading patterns (car PDF specific)
        skip_patterns = [
            r'^(page|p\.|fig|figure|table|see|cf|ibid|op\.?\s*cit|et\s+al)',
            r'^\d+
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,  # Just numbers
            r'^[^\w\s]+
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,  # Just punctuation
            r'^\w{1,2}
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,  # Very short words
            r'wikipedia|retrieved|accessed|archived',  # Wikipedia metadata
            r'^(january|february|march|april|may|june|july|august|september|october|november|december)',
            r'^\d{1,2}\/\d{1,2}\/\d{2,4}',  # Dates
            r'^https?://',  # URLs
            r'^(cc|hp|kw|rpm|mph|km/h|l|mm|cm|kg|lbs)[\s\d]',  # Technical units
            r'^(automatic|manual|cvt|dct|awd|fwd|rwd)
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,  # Transmission/drivetrain terms
            r'^(gasoline|diesel|hybrid|electric|petrol)
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,  # Fuel types
            r'^\$[\d,]+',  # Prices
        ]
        
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in skip_patterns):
            return False
        
        # Must be significantly larger than body text
        if font_size < font_analysis['heading_threshold']:
            return False
            
        # Look for car model section patterns
        major_section_patterns = [
            r'^(contents|table of contents)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(introduction|overview|summary|abstract)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(history|historical background|origins|development|background)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(design|styling|exterior|interior|body styles?)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(engines?|powertrain|performance|drivetrain|transmission)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(generation|gen)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(generation|gen)\s+(i{1,3}|iv|v|vi{1,3}|ix|x|\d+)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(mk|mark)\s+(\d+|i{1,3}|iv|v|vi{1,3})
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(model year|my)\s+\d{4}',
            r'^(sales|production|manufacturing|assembly)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(safety|crash tests?|ratings|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(specifications|specs|technical data|dimensions)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(trim levels?|variants|versions|models)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(racing|motorsport|competition|rally)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(reception|reviews|criticism|awards)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(discontinuation|end of production|retirement)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(facelift|refresh|update|redesign)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(concept|prototype|pre-production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^(see also|references|bibliography|further reading|external links|notes)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d+\.?\s+(introduction|history|design|engine|generation|safety|sales|production|specifications|racing|reception)',
            r'^(early|later|final|current|modern|contemporary)\s+(generation|model|version|production)
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
,
            r'^\d{4}[-–—]\d{4}',  # Year ranges like "2010-2015"
            r'^\d{4}[-–—]present',  # "2015-present"
        ]
        
        matches_major_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                                  for pattern in major_section_patterns)
        
        # Check if it looks like a proper title (title case)
        words = text.split()
        if len(words) >= 2:
            capitalized_ratio = sum(1 for word in words if word[0].isupper()) / len(words)
            is_title_case = capitalized_ratio >= 0.6
        else:
            is_title_case = text[0].isupper()
        
        # Only accept if it matches major patterns OR is clearly title case with good font size
        return matches_major_pattern or (is_title_case and font_size >= font_analysis['heading_threshold'] * 1.2)
    
    def split_large_section(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split very large sections into manageable chunks"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        # Try to split at paragraph boundaries first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for paragraph in paragraphs:
            para_words = len(paragraph.split())
            
            if current_words + para_words > self.max_words_per_chunk and current_chunk:
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = paragraph
                current_words = para_words
                chunk_num += 1
            else:
                current_chunk += ("\n\n" + paragraph if current_chunk else paragraph)
                current_words += para_words
        
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract major topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis:")
        print(f"  Body font: {font_analysis['body_font']}")
        print(f"  Heading threshold: {font_analysis['heading_threshold']}")
        print(f"  Font distribution: {font_analysis['font_distribution'][:5]}")
        
        # Extract all text with formatting
        all_lines = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0.0
                    
                    for span in line["spans"]:
                        if span["size"] >= self.min_font_size:
                            line_text += span["text"]
                            max_font_size = max(max_font_size, span["size"])
                    
                    line_text = line_text.strip()
                    if line_text and max_font_size > 0:
                        all_lines.append((line_text, max_font_size))
        
        # Process lines to identify major sections only
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        detected_headings = []
        
        for i, (text, font_size) in enumerate(all_lines):
            if self.is_major_heading(text, font_size, font_analysis):
                # Save previous section if it's substantial
                if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
                    chunks = self.split_large_section(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                elif current_section_text.strip():
                    # If section is too small, append to title for context
                    current_section_title = f"{current_section_title} - {text}"
                    current_section_text += text + "\n"
                    continue
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                detected_headings.append(f"'{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip() and len(current_section_text.split()) >= self.min_section_words:
            chunks = self.split_large_section(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        print(f"\nDetected {len(detected_headings)} major headings:")
        for heading in detected_headings:
            print(f"  - {heading}")
        
        doc.close()
        return sections

# Usage example with better defaults
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=800,      # Larger chunks
        min_section_words=100,        # Minimum words for a section to be valid
        font_threshold_ratio=1.5      # Must be 1.5x body font to be heading
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nFinal result: {len(chunks)} chunks from PDF")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        word_count = len(content.split())
        print(f"\n🔹 Chunk {i}: {heading}")
        print(f"📊 Words: {word_count}")
        print("-" * 50)
        print(content[:200] + "..." if len(content) > 200 else content)

# Example usage
if __name__ == "__main__":
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
