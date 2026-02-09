# Tax Return Tool

A Python-based tax calculation tool that reads tax documents from Google Drive, extracts tax data, and calculates Federal and California state taxes for tax year 2025.

## Features

- **Google Drive Integration**: Automatically download tax documents from a specified Google Drive folder
- **Document Parsing**: Extract text from PDFs, images (via OCR), and spreadsheets (CSV/Excel)
- **Tax Data Extraction**: Identify and extract data from W-2, 1099-INT, 1099-DIV, and 1099-NEC forms
- **Federal Tax Calculation**: Calculate federal income tax using 2025 tax brackets
- **California Tax Calculation**: Calculate California state tax including Mental Health Services Tax

## Installation

1. Clone or download this repository

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Tesseract OCR (required for image processing):
   - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
   - macOS: `brew install tesseract`
   - Linux: `sudo apt-get install tesseract-ocr`

## Google Drive Setup

To use Google Drive integration:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON file
6. Save it as `config/credentials.json`

## Usage

### Run Demo Mode
Run with sample data to see how the tool works:
```bash
python -m src.main --demo
```

### Process Local Files
Process tax documents from your local filesystem:
```bash
python -m src.main --files path/to/w2.pdf path/to/1099.pdf
```

### Process from Google Drive
Process tax documents from a Google Drive folder:
```bash
python -m src.main --folder-id YOUR_GOOGLE_DRIVE_FOLDER_ID
```

### Specify Filing Status
```bash
python -m src.main --demo --filing-status married_jointly
```

Available filing statuses:
- `single`
- `married_jointly`
- `married_separately`
- `head_of_household`

## Supported Document Types

| Document Type | Extension | Method |
|--------------|-----------|--------|
| PDF | .pdf | pdfplumber text extraction |
| JPEG | .jpg, .jpeg | Tesseract OCR |
| PNG | .png | Tesseract OCR |
| TIFF | .tiff, .tif | Tesseract OCR |
| CSV | .csv | pandas |
| Excel | .xlsx, .xls | pandas + openpyxl |

## Supported Tax Forms

- **W-2**: Wage and Tax Statement
- **1099-INT**: Interest Income
- **1099-DIV**: Dividends and Distributions
- **1099-NEC**: Nonemployee Compensation

## 2025 Tax Rates

### Federal Tax Brackets (Single)
| Income Range | Rate |
|-------------|------|
| $0 - $11,925 | 10% |
| $11,925 - $48,475 | 12% |
| $48,475 - $103,350 | 22% |
| $103,350 - $197,300 | 24% |
| $197,300 - $250,525 | 32% |
| $250,525 - $626,350 | 35% |
| Over $626,350 | 37% |

### California Tax Brackets (Single)
| Income Range | Rate |
|-------------|------|
| $0 - $10,756 | 1% |
| $10,756 - $25,499 | 2% |
| $25,499 - $40,245 | 4% |
| $40,245 - $55,866 | 6% |
| $55,866 - $70,606 | 8% |
| $70,606 - $360,659 | 9.3% |
| $360,659 - $432,787 | 10.3% |
| $432,787 - $721,314 | 11.3% |
| Over $721,314 | 12.3% |

Plus 1% Mental Health Services Tax on income over $1,000,000.

## Project Structure

```
tax-return-tool/
├── config/
│   └── credentials.json      # Google API credentials (user-provided)
├── src/
│   ├── __init__.py
│   ├── main.py               # Main entry point
│   ├── google_drive.py       # Google Drive API integration
│   ├── document_parser.py    # Document parsing (PDF/images/Excel)
│   ├── data_extractor.py     # Tax data extraction
│   ├── federal_tax.py        # Federal tax calculation
│   ├── california_tax.py     # California tax calculation
│   └── models.py             # Data models
├── requirements.txt
└── README.md
```

## Limitations

- Tax rates are estimates for 2025 based on inflation adjustments
- OCR accuracy depends on document quality
- Complex tax situations (itemized deductions, multiple states, etc.) may require manual adjustments
- This tool is for reference only and does not constitute tax advice

## Disclaimer

This tool is provided for educational and reference purposes only. It is not a substitute for professional tax advice. Tax laws are complex and subject to change. Always consult a qualified tax professional for your specific situation.

The tax brackets and deduction amounts used are estimates based on inflation adjustments from 2024 figures. Actual 2025 values may differ when officially published by the IRS and California Franchise Tax Board.
