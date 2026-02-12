"""Document parsing for tax forms (PDF, images, CSV/Excel)."""

import os
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

import pdfplumber
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

        Args:
            file_path: Path to the PDF file

        Returns:
            ParsedDocument with extracted content
        """
        text_content = []
        tables = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Extract text
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)

                # Extract tables
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table:
                        # Convert to DataFrame for easier processing
                        df = pd.DataFrame(table[1:], columns=table[0] if table else None)
                        tables.append(df)

        combined_text = '\n\n'.join(text_content)

        # If pdfplumber found no text, fall back to OCR (scanned PDF)
        if not combined_text.strip():
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(file_path)
                ocr_parts = []
                for img in images:
                    ocr_text = pytesseract.image_to_string(img)
                    if ocr_text:
                        ocr_parts.append(ocr_text)
                combined_text = '\n\n'.join(ocr_parts)
            except ImportError:
                # pdf2image not installed; try rendering with pdfplumber
                try:
                    with pdfplumber.open(file_path) as pdf2:
                        for page in pdf2.pages:
                            img = page.to_image(resolution=300).original
                            ocr_text = pytesseract.image_to_string(img)
                            if ocr_text:
                                text_content.append(ocr_text)
                    combined_text = '\n\n'.join(text_content)
                except Exception:
                    pass  # No OCR available

        return ParsedDocument(
            file_path=file_path,
            file_type='pdf',
            text_content=combined_text,
            tables=tables
        )

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
