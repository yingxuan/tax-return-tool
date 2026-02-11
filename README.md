# Tax Return Tool

A Python-based tax calculation tool that reads tax documents, extracts data, and calculates Federal and California state taxes for tax years 2024 and 2025.

## Features

- **YAML Configuration**: Define your taxpayer profile, filing status, dependents, and document folder in a single config file
- **Document Scanning**: Recursively scan a local folder with folder-aware categorization of tax documents
- **Document Parsing**: Extract text from PDFs, images (via OCR), and spreadsheets (CSV/Excel)
- **Tax Data Extraction**: Identify and extract data from W-2, 1099-INT, 1099-DIV, 1099-NEC, 1099-R, and 1098 forms
- **Federal Tax (Form 1040)**: Full calculation with standard or itemized deductions, qualified dividend rates, child tax credit, self-employment tax, and capital loss carryover
- **California Tax (Form 540)**: California brackets including Mental Health Services Tax, CA-specific itemized deductions (no SALT cap, excludes state income tax), and renter's credit
- **Schedule E**: Rental property income/expenses with 27.5-year straight-line depreciation (mid-month convention)
- **Schedule A**: Itemized deductions with federal SALT cap ($10K), mortgage interest (debt limit proration), CA vehicle license fee deduction, and charitable contributions
- **Estimated Tax Payments**: Track quarterly federal and California estimated payments
- **Dependent Care FSA**: Form 2441 dependent care benefit tracking
- **Report Generator**: Detailed tax summary report printed to console
- **Google Drive Integration**: Optionally download tax documents from Google Drive

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

## Configuration

Create a YAML config file (see `config/tax_profile.yaml`):

```yaml
tax_year: 2025

taxpayer:
  name: "John & Jane"
  filing_status: married_jointly
  age: 42
  is_ca_resident: true
  is_renter: false
  dependents: [Emily, Michael]

document_folder: "C:\\path\\to\\tax\\documents"

# 1098 forms with lender names matching these keywords are treated as rental mortgage
rental_1098_keywords: ["rental lender name"]

# Capital loss carryover from prior year (applied up to $3,000 per year)
capital_loss_carryover: 0

# Outstanding mortgage principal on personal residence (for $750K/$1M debt limit)
# Set to 0 to skip proration (e.g. if balance is under $750K)
personal_mortgage_balance: 0
```

## Usage

### Config-Driven Mode (Recommended)

Process tax documents using a YAML config file:
```bash
python -m src.main --config config/tax_profile.yaml
```

The config file specifies the taxpayer profile, document folder, and other settings. Documents are scanned, categorized, parsed, and tax calculations run automatically.

### Run Demo Mode

Run with comprehensive sample data (MFJ, 2 kids, W-2s, investments, rental property, itemized deductions):
```bash
python -m src.main --demo
```

### Process a Local Folder

Scan a folder recursively for tax documents:
```bash
python -m src.main --local-folder path/to/tax/docs
```

### Process Specific Files

Process individual tax documents:
```bash
python -m src.main --files path/to/w2.pdf path/to/1099.pdf
```

### Watch a Directory

Scan and categorize documents in a directory:
```bash
python -m src.main --watch path/to/tax/docs
```

### Process from Google Drive

Process tax documents from a Google Drive folder:
```bash
python -m src.main --folder-id YOUR_GOOGLE_DRIVE_FOLDER_ID
```

### CLI Overrides

Override config settings from the command line:
```bash
python -m src.main --config config/tax_profile.yaml --filing-status single --tax-year 2024
```

Available filing statuses: `single`, `married_jointly`, `married_separately`, `head_of_household`

Supported tax years: `2024`, `2025`

## Supported Document Types

| Document Type | Extension | Method |
|--------------|-----------|--------|
| PDF | .pdf | pdfplumber text extraction |
| JPEG | .jpg, .jpeg | Tesseract OCR |
| PNG | .png | Tesseract OCR |
| TIFF | .tiff, .tif | Tesseract OCR |
| BMP | .bmp | Tesseract OCR |
| CSV | .csv | pandas |
| Excel | .xlsx, .xls | pandas + openpyxl |

## Supported Tax Forms

- **W-2**: Wage and Tax Statement
- **1099-INT**: Interest Income
- **1099-DIV**: Dividends and Distributions (including qualified dividends and capital gains)
- **1099-NEC**: Nonemployee Compensation
- **1099-R**: Distributions from Pensions, Annuities, Retirement Plans
- **1098**: Mortgage Interest Statement (auto-tagged as personal or rental via config keywords)

## Google Drive Setup

To use Google Drive integration:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Drive API
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON file
6. Save it as `config/credentials.json`

## Project Structure

```
tax-return-tool/
├── config/
│   ├── credentials.json      # Google API credentials (user-provided)
│   └── tax_profile.yaml      # Taxpayer profile configuration
├── src/
│   ├── __init__.py
│   ├── main.py               # Main entry point & CLI
│   ├── config_loader.py      # YAML config loader
│   ├── google_drive.py       # Google Drive API integration
│   ├── document_parser.py    # Document parsing (PDF/images/Excel)
│   ├── data_extractor.py     # Tax data extraction from documents
│   ├── file_watcher.py       # Folder scanning & document categorization
│   ├── models.py             # Data models (TaxReturn, forms, etc.)
│   ├── federal_tax.py        # Federal tax calculation (Form 1040)
│   ├── california_tax.py     # California tax calculation (Form 540)
│   ├── schedule_e.py         # Schedule E (rental property income)
│   ├── schedule_a.py         # Schedule A (itemized deductions)
│   └── report_generator.py   # Tax report output
├── test_tax_calculation.py   # Tax calculation tests
├── requirements.txt
└── README.md
```

## Testing

Run the test suite:
```bash
python test_tax_calculation.py
```

## Limitations

- OCR accuracy depends on document quality
- Complex tax situations (AMT, foreign income, multiple states) may require manual adjustments
- This tool is for reference only and does not constitute tax advice

## Disclaimer

This tool is provided for educational and reference purposes only. It is not a substitute for professional tax advice. Tax laws are complex and subject to change. Always consult a qualified tax professional for your specific situation.
