"""Document parsing for tax forms (PDF, images, CSV/Excel)."""

import os
import warnings
import logging
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

import pdfplumber

# Suppress noisy PDF font warnings (missing FontBBox in descriptor)
for _name in ("pdfminer", "pdfminer.six", "pdfplumber", "pypdf", "PyPDF2"):
    logging.getLogger(_name).setLevel(logging.ERROR)
import pytesseract
from PIL import Image
import pandas as pd


@dataclass
class ParsedDocument:
    """Container for parsed document content."""
    file_path: str
    file_type: str
    text_content: str
    tables: list  # List of DataFrames or list of lists
    raw_data: Optional[pd.DataFrame] = None  # For CSV/Excel files


class DocumentParser:
    """Parse various document types to extract text and tables."""

    # File type mappings
    PDF_EXTENSIONS = {'.pdf'}
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    SPREADSHEET_EXTENSIONS = {'.csv', '.xlsx', '.xls'}

    # Common Tesseract install locations on Windows
    _TESSERACT_PATHS = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]

    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialize the document parser.

        Args:
            tesseract_path: Path to Tesseract executable (if not in PATH)
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            # Auto-detect Tesseract on Windows if not in PATH
            for candidate in self._TESSERACT_PATHS:
                if os.path.isfile(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break

    def parse(self, file_path: str) -> ParsedDocument:
        """
        Parse a document and extract its content.

        Args:
            file_path: Path to the document file

        Returns:
            ParsedDocument containing extracted text and tables
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension in self.PDF_EXTENSIONS:
            return self._parse_pdf(file_path)
        elif extension in self.IMAGE_EXTENSIONS:
            return self._parse_image(file_path)
        elif extension in self.SPREADSHEET_EXTENSIONS:
            return self._parse_spreadsheet(file_path)
        else:
            raise ValueError(f"Unsupported file type: {extension}")

    def _parse_pdf(self, file_path: str) -> ParsedDocument:
        """
        Parse a PDF file to extract text and tables.

        Text extraction priority:
          1. Spatial reconstruction — sorts all characters by (y, x) position,
             correctly separating columns that pdfplumber's default stream order
             interleaves.  Used when it produces clean, substantial text.
          2. High-resolution OCR (300 DPI) — authoritative source for image-based
             PDFs and any PDF where spatial reconstruction is garbled or empty.

        The legacy pdfplumber default stream order is NOT used for final text;
        it is retained only for structured table extraction.
        """
        tables = []

        # Extract structured tables via pdfplumber (independent of text order)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*[Ff]ont[Bb]ox.*")
            warnings.filterwarnings("ignore", message=".*font descriptor.*")
            with pdfplumber.open(file_path) as pdf:
                num_pages = max(len(pdf.pages), 1)
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    for table in page_tables:
                        if table:
                            df = pd.DataFrame(table[1:], columns=table[0] if table else None)
                            tables.append(df)

        # --- Text extraction: spatial first, OCR as high-priority fallback ---

        # Step 1: Spatial reconstruction (best for text-based PDFs)
        spatial = self._parse_pdf_spatial(file_path)
        spatial_ok = (
            bool(spatial.strip())
            and not self._is_garbled(spatial)
            and len(spatial.strip()) >= 200 * num_pages
        )

        if spatial_ok:
            combined_text = spatial
        else:
            # Step 2: High-resolution OCR — prioritised over garbled/thin/empty spatial
            ocr_text = self._ocr_pdf(file_path)
            if ocr_text.strip():
                combined_text = ocr_text
            else:
                # Last resort: fall back to whatever spatial produced
                combined_text = spatial

        return ParsedDocument(
            file_path=file_path,
            file_type='pdf',
            text_content=combined_text,
            tables=tables
        )

    @staticmethod
    def _is_garbled(text: str) -> bool:
        """Return True if the text looks like garbled PDF column-extraction.

        PDFs with multi-column layouts sometimes yield a stream of single
        characters on separate lines (e.g. 'Z\\nP\\nI\\nA\\n...') instead of
        readable words.  If more than 40% of non-empty lines are ≤ 2 chars,
        the text is considered garbled and OCR should be preferred.
        """
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return False
        short = sum(1 for ln in lines if len(ln.strip()) <= 2)
        return (short / len(lines)) > 0.40

    def _parse_pdf_spatial(self, file_path: str) -> str:
        """Re-extract PDF text by sorting characters spatially (row then column).

        pdfplumber's default extraction reads characters in the order they appear
        in the PDF content stream, which for multi-column forms interleaves chars
        from adjacent columns.  Sorting by (y_top rounded to nearest 5pt, x0)
        reconstructs the visual reading order.
        """
        page_texts = []
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        chars = page.chars
                        if not chars:
                            continue
                        # Round y to nearest 5pt to group chars on the same line
                        rows: dict = {}
                        for ch in chars:
                            row_key = round(ch['top'] / 5) * 5
                            rows.setdefault(row_key, []).append(ch)
                        lines = []
                        for y in sorted(rows):
                            row_chars = sorted(rows[y], key=lambda c: c['x0'])
                            # Insert a space when the gap between two chars
                            # exceeds 30% of the font size — word boundary.
                            parts = []
                            prev_x1 = None
                            prev_size = None
                            for ch in row_chars:
                                if prev_x1 is not None:
                                    gap = ch['x0'] - prev_x1
                                    avg_size = ((ch.get('size') or 10) + (prev_size or 10)) / 2
                                    if gap > avg_size * 0.3:
                                        parts.append(' ')
                                parts.append(ch['text'])
                                prev_x1 = ch['x1']
                                prev_size = ch.get('size') or 10
                            lines.append(''.join(parts))
                        page_texts.append('\n'.join(lines))
        except Exception:
            return ''
        return '\n\n'.join(page_texts)

    def _ocr_pdf(self, file_path: str) -> str:
        """Render each PDF page as an image and run Tesseract OCR on it."""
        parts = []
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path, dpi=300)
        except ImportError:
            # pdf2image not installed — render via pdfplumber
            images = []
            try:
                with pdfplumber.open(file_path) as pdf2:
                    for page in pdf2.pages:
                        images.append(page.to_image(resolution=300).original)
            except Exception:
                return ''
        for img in images:
            ocr_text = pytesseract.image_to_string(img)
            if ocr_text:
                parts.append(ocr_text)
        return '\n\n'.join(parts)

    def _parse_image(self, file_path: str) -> ParsedDocument:
        """
        Parse an image file using OCR.

        Args:
            file_path: Path to the image file

        Returns:
            ParsedDocument with OCR-extracted text
        """
        # Open and preprocess image
        image = Image.open(file_path)

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Perform OCR
        text_content = pytesseract.image_to_string(image)

        # Try to extract structured data (tables)
        # Use pytesseract's data extraction for bounding boxes
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        return ParsedDocument(
            file_path=file_path,
            file_type='image',
            text_content=text_content,
            tables=[]  # Image table extraction is complex, rely on text parsing
        )

    def _parse_spreadsheet(self, file_path: str) -> ParsedDocument:
        """
        Parse a CSV or Excel file.

        Args:
            file_path: Path to the spreadsheet file

        Returns:
            ParsedDocument with structured data
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        if extension == '.csv':
            # Read without header to handle key-value format CSVs
            df = pd.read_csv(file_path, header=None)
        else:  # Excel
            df = pd.read_excel(file_path, header=None)

        # Convert DataFrame to text representation
        text_content = df.to_string()

        return ParsedDocument(
            file_path=file_path,
            file_type='spreadsheet',
            text_content=text_content,
            tables=[df],
            raw_data=df
        )

    def parse_multiple(self, file_paths: list) -> list:
        """
        Parse multiple documents.

        Args:
            file_paths: List of file paths to parse

        Returns:
            List of ParsedDocument objects
        """
        results = []
        for file_path in file_paths:
            try:
                parsed = self.parse(file_path)
                results.append(parsed)
                # Use ASCII-safe path for print (Windows cp1252 can't handle some Unicode)
                safe_path = file_path.encode('ascii', errors='replace').decode('ascii')
                print(f"Successfully parsed: {safe_path}")
            except Exception as e:
                safe_path = file_path.encode('ascii', errors='replace').decode('ascii')
                print(f"Error parsing {safe_path}: {e}")
        return results


class OCREnhancer:
    """Enhance OCR results for tax documents."""

    # Common OCR corrections for tax forms
    COMMON_CORRECTIONS = {
        'W-Z': 'W-2',
        'W2': 'W-2',
        'l099': '1099',
        '1O99': '1099',
        'lO99': '1099',
        'S0CIAL': 'SOCIAL',
        'SECUR1TY': 'SECURITY',
    }

    @classmethod
    def correct_text(cls, text: str) -> str:
        """
        Apply common corrections to OCR text.

        Args:
            text: Raw OCR text

        Returns:
            Corrected text
        """
        corrected = text
        for wrong, right in cls.COMMON_CORRECTIONS.items():
            corrected = corrected.replace(wrong, right)
        return corrected

    @classmethod
    def extract_numbers(cls, text: str) -> list:
        """
        Extract monetary values from text.

        Args:
            text: Text containing potential monetary values

        Returns:
            List of extracted float values
        """
        import re

        # Pattern for monetary values (with optional $ and commas)
        pattern = r'\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        matches = re.findall(pattern, text)

        values = []
        for match in matches:
            # Remove $ and commas
            clean = match.replace('$', '').replace(',', '')
            try:
                values.append(float(clean))
            except ValueError:
                continue

        return values
