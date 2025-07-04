import fitz
import re
from collections import Counter
from typing import List, Tuple, Dict

class WikipediaPDFChunker:
    def __init__(self, 
                 min_font_size: float = 6.0, 
                 max_words_per_chunk: int = 500,
                 min_heading_chars: int = 3,
                 max_heading_chars: int = 200):
        self.min_font_size = min_font_size
        self.max_words_per_chunk = max_words_per_chunk
        self.min_heading_chars = min_heading_chars
        self.max_heading_chars = max_heading_chars
        
    def analyze_font_structure(self, doc) -> Dict:
        """Analyze the document to understand font patterns"""
        font_sizes = []
        text_patterns = []
        
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
                        font_sizes.append(max_font_size)
                        text_patterns.append((line_text, max_font_size))
        
        # Find common font sizes
        font_counter = Counter([round(size, 1) for size in font_sizes])
        sorted_fonts = sorted(font_counter.items(), key=lambda x: x[1], reverse=True)
        
        # Determine body text font (most common)
        body_font = sorted_fonts[0][0] if sorted_fonts else 10.0
        
        # Find potential heading fonts (larger than body text)
        heading_fonts = [size for size, count in sorted_fonts 
                        if size > body_font and count >= 2]
        
        return {
            'body_font': body_font,
            'heading_fonts': heading_fonts,
            'all_fonts': sorted_fonts,
            'text_patterns': text_patterns
        }
    
    def is_likely_heading(self, text: str, font_size: float, font_analysis: Dict, 
                         next_lines: List[Tuple[str, float]]) -> bool:
        """Determine if a line is likely a heading using multiple criteria"""
        
        # Basic length check
        if len(text) < self.min_heading_chars or len(text) > self.max_heading_chars:
            return False
            
        # Skip if it's just numbers or very short
        if re.match(r'^\d+\.?\s*$', text) or len(text.split()) < 2:
            return False
            
        body_font = font_analysis['body_font']
        heading_fonts = font_analysis['heading_fonts']
        
        # Font size criteria
        is_larger_font = font_size > body_font + 0.5
        is_heading_font = any(abs(font_size - hf) < 0.5 for hf in heading_fonts)
        
        # Check if next lines have smaller fonts (heading pattern)
        has_smaller_following = True
        if next_lines:
            next_fonts = [nf for _, nf in next_lines[:3]]  # Check next 3 lines
            has_smaller_following = all(font_size >= nf for nf in next_fonts)
        
        # Pattern-based detection
        heading_patterns = [
            # Wikipedia section patterns
            r'^\d+\.?\s+[A-Z]',  # "1. History" or "1 History"
            r'^[A-Z][a-z]+(\s+[a-z]+)*$',  # "History", "Early life"
            r'^[A-Z][a-z]+(\s+[a-z]+)*\s*$',  # With trailing space
            r'^\d+\.\d+\s+[A-Z]',  # "1.1 Early years"
            # Common Wikipedia sections
            r'^(History|Biography|Career|Personal life|Legacy|Death|Birth|Education|Works|Awards|References|See also|External links|Notes|Further reading|Bibliography|Contents|Overview|Background|Development|Impact|Reception|Criticism|Analysis|Methodology|Results|Conclusion|Introduction|Summary|Abstract)(\s|$)',
            r'^(Early|Later|Recent|Modern|Contemporary|Ancient|Medieval|Current|Future)\s+(life|career|years|period|era|work|development)',
        ]
        
        matches_pattern = any(re.match(pattern, text, re.IGNORECASE) 
                            for pattern in heading_patterns)
        
        # Title case check (most words capitalized)
        words = text.split()
        if len(words) >= 2:
            capitalized_words = sum(1 for word in words 
                                  if word[0].isupper() and len(word) > 1)
            title_case_ratio = capitalized_words / len(words)
            is_title_case = title_case_ratio >= 0.6
        else:
            is_title_case = text[0].isupper() if text else False
        
        # Combine criteria
        score = 0
        if is_larger_font or is_heading_font: score += 2
        if has_smaller_following: score += 1
        if matches_pattern: score += 3
        if is_title_case: score += 1
        
        return score >= 3
    
    def split_into_chunks(self, title: str, text: str) -> List[Tuple[str, str]]:
        """Split large text into smaller chunks while preserving meaning"""
        words = text.split()
        if len(words) <= self.max_words_per_chunk:
            return [(title, text)]
        
        chunks = []
        sentences = re.split(r'[.!?]+\s+', text)
        current_chunk = ""
        current_words = 0
        chunk_num = 1
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            
            if current_words + sentence_words > self.max_words_per_chunk and current_chunk:
                # Save current chunk
                chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
                chunks.append((chunk_title, current_chunk.strip()))
                current_chunk = sentence
                current_words = sentence_words
                chunk_num += 1
            else:
                current_chunk += (" " + sentence if current_chunk else sentence)
                current_words += sentence_words
        
        # Add remaining text
        if current_chunk.strip():
            chunk_title = title if chunk_num == 1 else f"{title} (Part {chunk_num})"
            chunks.append((chunk_title, current_chunk.strip()))
        
        return chunks
    
    def extract_smart_chunks(self, pdf_path: str) -> List[Tuple[str, str]]:
        """Extract topic-based chunks from Wikipedia PDF"""
        doc = fitz.open(pdf_path)
        
        # Analyze font structure
        font_analysis = self.analyze_font_structure(doc)
        print(f"Font analysis: Body={font_analysis['body_font']}, Headings={font_analysis['heading_fonts']}")
        
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
        
        # Process lines to identify sections
        sections = []
        current_section_title = "Introduction"
        current_section_text = ""
        
        for i, (text, font_size) in enumerate(all_lines):
            # Get next few lines for context
            next_lines = all_lines[i+1:i+4] if i+1 < len(all_lines) else []
            
            if self.is_likely_heading(text, font_size, font_analysis, next_lines):
                # Save previous section
                if current_section_text.strip():
                    chunks = self.split_into_chunks(current_section_title, current_section_text.strip())
                    sections.extend(chunks)
                
                # Start new section
                current_section_title = text
                current_section_text = ""
                print(f"Found heading: '{text}' (font: {font_size})")
            else:
                current_section_text += text + "\n"
        
        # Save final section
        if current_section_text.strip():
            chunks = self.split_into_chunks(current_section_title, current_section_text.strip())
            sections.extend(chunks)
        
        doc.close()
        return sections

# Usage example
def process_pdf(pdf_path: str):
    chunker = WikipediaPDFChunker(
        min_font_size=6.0,
        max_words_per_chunk=500,
        min_heading_chars=3,
        max_heading_chars=200
    )
    
    chunks = chunker.extract_smart_chunks(pdf_path)
    
    print(f"\nExtracted {len(chunks)} chunks:")
    print("=" * 60)
    
    for i, (heading, content) in enumerate(chunks, 1):
        print(f"\n🔹 Chunk {i}: {heading}")
        print("-" * 50)
        print(content[:300] + "..." if len(content) > 300 else content)
        print(f"\n📊 Words: {len(content.split())}")

# Example usage
if __name__ == "__main__":
    # Replace with your PDF path
    pdf_path = "your_wikipedia_pdf.pdf"
    process_pdf(pdf_path)
