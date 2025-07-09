import pdfplumber
import re
import json
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import argparse

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float
    
    def to_dict(self):
        return {
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height
        }

@dataclass
class InfoboxData:
    title: str
    bbox: BoundingBox
    data: Dict[str, str]
    raw_text: str
    page_number: int
    
    def to_dict(self):
        return {
            'title': self.title,
            'bbox': self.bbox.to_dict(),
            'data': self.data,
            'raw_text': self.raw_text,
            'page_number': self.page_number
        }

class CarInfoboxExtractor:
    def __init__(self):
        # Car-specific infobox field patterns
        self.field_patterns = {
            # Basic info
            'manufacturer': r'(?:Manufacturer|Make)[:\s]+([^\n]+)',
            'model': r'Model[:\s]+([^\n]+)',
            'year': r'(?:Year|Model year)[:\s]+([^\n]+)',
            'production': r'Production[:\s]+([^\n]+)',
            'class': r'(?:Class|Category)[:\s]+([^\n]+)',
            'body_style': r'Body style[:\s]+([^\n]+)',
            'layout': r'Layout[:\s]+([^\n]+)',
            'platform': r'Platform[:\s]+([^\n]+)',
            'related': r'Related[:\s]+([^\n]+)',
            
            # Engine specifications
            'engine': r'Engine[:\s]+([^\n]+)',
            'displacement': r'Displacement[:\s]+([^\n]+)',
            'power': r'(?:Power|Horsepower)[:\s]+([^\n]+)',
            'torque': r'Torque[:\s]+([^\n]+)',
            'fuel_system': r'Fuel system[:\s]+([^\n]+)',
            'fuel_type': r'Fuel type[:\s]+([^\n]+)',
            'fuel_capacity': r'Fuel capacity[:\s]+([^\n]+)',
            'compression': r'Compression[:\s]+([^\n]+)',
            
            # Transmission
            'transmission': r'Transmission[:\s]+([^\n]+)',
            'drivetrain': r'(?:Drivetrain|Drive)[:\s]+([^\n]+)',
            
            # Dimensions
            'length': r'Length[:\s]+([^\n]+)',
            'width': r'Width[:\s]+([^\n]+)',
            'height': r'Height[:\s]+([^\n]+)',
            'wheelbase': r'Wheelbase[:\s]+([^\n]+)',
            'ground_clearance': r'Ground clearance[:\s]+([^\n]+)',
            'curb_weight': r'(?:Curb weight|Weight)[:\s]+([^\n]+)',
            'gross_weight': r'Gross weight[:\s]+([^\n]+)',
            
            # Performance
            'top_speed': r'Top speed[:\s]+([^\n]+)',
            'acceleration': r'(?:0-60|0-100|Acceleration)[:\s]+([^\n]+)',
            'fuel_economy': r'(?:Fuel economy|MPG)[:\s]+([^\n]+)',
            'range': r'Range[:\s]+([^\n]+)',
            
            # Other specs
            'doors': r'Doors[:\s]+([^\n]+)',
            'seating': r'(?:Seating|Seats)[:\s]+([^\n]+)',
            'price': r'(?:Price|MSRP)[:\s]+([^\n]+)',
            'successor': r'Successor[:\s]+([^\n]+)',
            'predecessor': r'Predecessor[:\s]+([^\n]+)',
            'designer': r'Designer[:\s]+([^\n]+)',
            'assembly': r'Assembly[:\s]+([^\n]+)',
        }
        
        # Title patterns to identify car model names
        self.title_patterns = [
            r'^([A-Z][A-Za-z0-9\s\-]{3,40})\s*\n',  # Car model names
            r'^\s*([A-Z][A-Za-z0-9\s\-]{3,40})\s*\n',
        ]
    
    def extract_from_pdf(self, pdf_path: str) -> List[InfoboxData]:
        """Extract all car infoboxes from a PDF file"""
        infoboxes = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_infoboxes = self._extract_from_page(page, page_num + 1)
                    infoboxes.extend(page_infoboxes)
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")
        
        return infoboxes
    
    def _extract_from_page(self, page, page_number: int) -> List[InfoboxData]:
        """Extract infoboxes from a single page"""
        infoboxes = []
        
        # Get page dimensions
        page_width = page.width
        page_height = page.height
        
        # Extract text with character-level positioning
        chars = page.chars
        
        # Filter characters that are likely in the right column (typical infobox location)
        right_threshold = page_width * 0.55  # Adjust this threshold as needed
        right_chars = [c for c in chars if c['x0'] > right_threshold]
        
        if not right_chars:
            return infoboxes
        
        # Group characters into text blocks
        text_blocks = self._group_chars_into_blocks(right_chars)
        
        for block in text_blocks:
            if self._is_likely_infobox(block['text']):
                infobox = self._parse_infobox(block, page_number)
                if infobox:
                    infoboxes.append(infobox)
        
        return infoboxes
    
    def _group_chars_into_blocks(self, chars: List[Dict]) -> List[Dict]:
        """Group characters into coherent text blocks"""
        if not chars:
            return []
        
        # Sort characters by position
        chars.sort(key=lambda c: (c['top'], c['x0']))
        
        blocks = []
        current_block = {
            'chars': [chars[0]],
            'bbox': {
                'x0': chars[0]['x0'],
                'y0': chars[0]['top'],
                'x1': chars[0]['x1'],
                'y1': chars[0]['bottom']
            }
        }
        
        for char in chars[1:]:
            # Check if this character belongs to the current block
            if (abs(char['top'] - current_block['bbox']['y1']) < 10 and  # Close vertically
                abs(char['x0'] - current_block['bbox']['x1']) < 50):    # Close horizontally
                
                # Add to current block
                current_block['chars'].append(char)
                current_block['bbox']['x1'] = max(current_block['bbox']['x1'], char['x1'])
                current_block['bbox']['y1'] = max(current_block['bbox']['y1'], char['bottom'])
            else:
                # Start new block
                current_block['text'] = ''.join(c['text'] for c in current_block['chars'])
                blocks.append(current_block)
                
                current_block = {
                    'chars': [char],
                    'bbox': {
                        'x0': char['x0'],
                        'y0': char['top'],
                        'x1': char['x1'],
                        'y1': char['bottom']
                    }
                }
        
        # Add the last block
        current_block['text'] = ''.join(c['text'] for c in current_block['chars'])
        blocks.append(current_block)
        
        return blocks
    
    def _is_likely_infobox(self, text: str) -> bool:
        """Check if text block is likely an infobox"""
        # Look for car-specific keywords
        car_keywords = [
            'engine', 'transmission', 'horsepower', 'torque', 'displacement',
            'manufacturer', 'model', 'production', 'wheelbase', 'length',
            'width', 'height', 'weight', 'fuel', 'mpg', 'acceleration',
            'top speed', 'drivetrain', 'doors', 'seating'
        ]
        
        text_lower = text.lower()
        keyword_count = sum(1 for keyword in car_keywords if keyword in text_lower)
        
        # Also check for typical infobox structure (key: value pairs)
        colon_count = text.count(':')
        
        return keyword_count >= 2 or colon_count >= 3
    
    def _parse_infobox(self, block: Dict, page_number: int) -> Optional[InfoboxData]:
        """Parse a text block into structured infobox data"""
        text = block['text']
        
        # Extract title (usually first line)
        title = self._extract_title(text)
        
        # Extract structured data
        data = self._extract_structured_data(text)
        
        if not data:
            return None
        
        # Create bounding box
        bbox = BoundingBox(
            x=block['bbox']['x0'],
            y=block['bbox']['y0'],
            width=block['bbox']['x1'] - block['bbox']['x0'],
            height=block['bbox']['y1'] - block['bbox']['y0']
        )
        
        return InfoboxData(
            title=title,
            bbox=bbox,
            data=data,
            raw_text=text,
            page_number=page_number
        )
    
    def _extract_title(self, text: str) -> str:
        """Extract the title from infobox text"""
        lines = text.split('\n')
        
        for pattern in self.title_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        # Fallback: use first non-empty line
        for line in lines:
            line = line.strip()
            if line and len(line) > 3:
                return line
        
        return "Unknown Car Model"
    
    def _extract_structured_data(self, text: str) -> Dict[str, str]:
        """Extract key-value pairs from infobox text"""
        data = {}
        
        # Use predefined patterns
        for key, pattern in self.field_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                # Clean up the value
                value = re.sub(r'\s+', ' ', value)  # Normalize whitespace
                data[key] = value
        
        # Also try to extract other key-value pairs
        generic_pattern = r'([A-Za-z\s]+?):\s*([^\n]+)'
        matches = re.findall(generic_pattern, text)
        
        for key, value in matches:
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()
            
            if key and value and key not in data:
                data[key] = value
        
        return data
    
    def process_directory(self, directory_path: str, output_file: str = None):
        """Process all PDF files in a directory"""
        results = []
        
        pdf_files = [f for f in os.listdir(directory_path) if f.lower().endswith('.pdf')]
        
        print(f"Found {len(pdf_files)} PDF files to process...")
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(directory_path, pdf_file)
            print(f"Processing: {pdf_file}")
            
            infoboxes = self.extract_from_pdf(pdf_path)
            
            result = {
                'filename': pdf_file,
                'infoboxes': [infobox.to_dict() for infobox in infoboxes]
            }
            results.append(result)
            
            print(f"  Found {len(infoboxes)} infoboxes")
        
        # Save results
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}")
        
        return results
    
    def print_summary(self, results: List[Dict]):
        """Print a summary of extracted data"""
        total_files = len(results)
        total_infoboxes = sum(len(r['infoboxes']) for r in results)
        
        print(f"\n=== EXTRACTION SUMMARY ===")
        print(f"Total files processed: {total_files}")
        print(f"Total infoboxes found: {total_infoboxes}")
        
        # Show sample data
        for result in results[:3]:  # Show first 3 files
            if result['infoboxes']:
                print(f"\n{result['filename']}:")
                for i, infobox in enumerate(result['infoboxes'][:2]):  # Show first 2 infoboxes
                    print(f"  Infobox {i+1}: {infobox['title']}")
                    print(f"    Fields: {', '.join(infobox['data'].keys())}")

def main():
    parser = argparse.ArgumentParser(description='Extract car infoboxes from Wikipedia PDFs')
    parser.add_argument('input_path', help='Path to PDF file or directory containing PDFs')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    extractor = CarInfoboxExtractor()
    
    if os.path.isfile(args.input_path):
        # Process single file
        infoboxes = extractor.extract_from_pdf(args.input_path)
        results = [{
            'filename': os.path.basename(args.input_path),
            'infoboxes': [infobox.to_dict() for infobox in infoboxes]
        }]
    else:
        # Process directory
        results = extractor.process_directory(args.input_path, args.output)
    
    if args.verbose:
        extractor.print_summary(results)
    
    if args.output and os.path.isfile(args.input_path):
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
