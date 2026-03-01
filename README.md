# Tax Return Tool

A local, privacy-first tax calculator that reads your actual tax documents (W-2s, 1099s, 1098s, etc.) and computes your Federal (Form 1040) and state taxes for **2024 and 2025**.

> **100% offline.** No documents, OCR results, or tax data ever leave your machine. You can disconnect from the internet before running it.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/yingxuan/tax-return-tool.git
cd tax-return-tool

# 2. Install everything (Tesseract OCR + Python packages)
make install

# 3. Launch the browser UI
make web
```

Then open **http://localhost:5000** in your browser.

> **Windows users:** `make install` installs Python packages automatically. For Tesseract, download and run the installer from https://github.com/UB-Mannheim/tesseract/wiki, then re-run `make web`.

---

## What It Does

Point it at a folder of tax documents and it:

1. Scans PDFs, images (via OCR), and spreadsheets
2. Identifies and extracts data from W-2, 1099, and 1098 forms
3. Runs the full Federal (1040) and state tax calculation
4. Outputs a detailed tax summary report
5. Optionally fills out the actual IRS/CA PDF forms

**Supported states:** California (Form 540), New York (IT-201). Other states show withholding totals only.

---

## Installation (detailed)

### Python packages

```bash
pip install -r requirements.txt
```

### Tesseract OCR

Required for processing image files and scanned PDFs.

| OS | Command |
|----|---------|
| macOS | `brew install tesseract` |
| Linux (Debian/Ubuntu) | `sudo apt-get install tesseract-ocr` |
| Windows | [Download installer](https://github.com/UB-Mannheim/tesseract/wiki) |

`make install` handles the macOS and Linux steps automatically.

### Virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
make install
```

---

## Usage

### Web UI (easiest)

```bash
make web          # or: python -m src.ui_app
```

Open http://localhost:5000. Supports manual entry, folder scanning, and drag-and-drop file upload. No config file required.

### Config-driven mode (recommended for repeat use)

Create a `config/tax_profile.yaml` (see [Configuration](#configuration) below), then:

```bash
python -m src.main --config config/tax_profile.yaml
```

### Demo mode (no documents needed)

```bash
make demo         # or: python -m src.main --demo
```

Runs a full calculation with built-in sample data: married filing jointly, two dependents, W-2 income, investments, and a rental property.

### Other CLI options

```bash
# Scan a local folder of documents
python -m src.main --local-folder path/to/tax/docs

# Process specific files
python -m src.main --files w2.pdf 1099-div.pdf

# Override config values from the command line
python -m src.main --config tax_profile.yaml --filing-status single --tax-year 2024
```

Available filing statuses: `single`, `married_jointly`, `married_separately`, `head_of_household`

---

## Configuration

Create a YAML file to describe your tax situation. The tool uses it to fill in data that can't be extracted from documents (purchase price, carryovers, etc.) and to avoid re-entering your profile each time.

```yaml
tax_year: 2025

taxpayer:
  name: "Jane & John Doe"
  filing_status: married_jointly   # single | married_jointly | married_separately | head_of_household
  age: 42
  is_ca_resident: true
  is_renter: false
  dependents:
    - name: "Alice Doe"
      age: 8
      relationship: "daughter"

# Folder containing your tax documents (PDFs, images, spreadsheets)
document_folder: "/path/to/tax/documents"

# Capital loss carryover from prior year (up to $3,000 deductible per year)
short_term_loss_carryover: 0
long_term_loss_carryover: 0

# Prior-year passive activity loss carryover (Form 8582)
pal_carryover: 0

# Outstanding mortgage balance on primary residence
# Used to prorate deductible interest when balance exceeds $750K ($1M for pre-2018 loans)
# Set to 0 to skip proration
personal_mortgage_balance: 0

# Cash charitable contributions not captured in documents
charitable_contributions: 0

# Federal and CA estimated tax payments made during the year
federal_estimated_payments: 0
ca_estimated_payments: 0

# Rental properties (Schedule E)
# property_tax and insurance are auto-extracted from documents when possible
rental_properties:
  - address: "123 Rental St, Sunnyvale, CA 94087"
    property_type: "Single Family"
    purchase_price: 900000
    purchase_date: "2018-06-01"
    land_value: 180000        # Purchase price minus depreciable basis
    rental_income: 36000      # Annual gross rent (if not in documents)
    other_expenses: 0         # Miscellaneous expenses not in documents
```

See `config/tax_profile.yaml` for a fuller example.

---

## Supported Documents

| Form | Description | Extracted Fields |
|------|-------------|-----------------|
| **W-2** | Wages & withholding | Box 1, 2, 12, 16, 17 |
| **1099-INT** | Interest income | Box 1, 4 |
| **1099-DIV** | Dividends | Box 1a, 1b, 2a, 4 |
| **1099-NEC** | Self-employment income | Box 1 |
| **1099-R** | Retirement distributions | Box 1, 2a, 4 |
| **1098** | Mortgage interest | Box 1, 5, 10; rental auto-tagged by property address |
| **1099-B / Composite** | Brokerage sales | Proceeds, basis, gain/loss |
| **Property tax bill** | Real estate taxes | Amount, parcel address |
| **Home insurance** | Insurance premium | Annual premium |
| **Vehicle registration** | CA vehicle license fee | Deductible fee amount |

**File formats:** PDF (text), PDF (scanned/image via OCR), JPEG, PNG, TIFF, BMP, CSV, Excel (.xlsx/.xls)

---

## Features

- **Federal Form 1040**: Standard or itemized deductions, qualified dividend tax rates, child tax credit, self-employment tax, capital loss carryover
- **Schedule A**: SALT cap ($10K federal), mortgage interest with debt-limit proration, CA vehicle license fee, charitable contributions
- **Schedule E**: Rental income/expenses, 27.5-year straight-line depreciation (mid-month convention), passive activity loss carryover
- **California Form 540**: CA tax brackets, Mental Health Services Tax, CA-specific deductions (no SALT cap, no state income tax deduction), renter's credit
- **New York IT-201**: NY state and NYC tax calculation
- **PDF form output**: Fills and saves the actual IRS 1040 and CA 540 PDF forms
- **Web UI**: Browser interface with manual entry, folder scanning, drag-and-drop upload, and downloadable report

---

## Project Structure

```
tax-return-tool/
├── config/
│   └── tax_profile.yaml        # Example taxpayer profile
├── src/
│   ├── main.py                 # CLI entry point
│   ├── ui_app.py               # Flask web UI
│   ├── config_loader.py        # YAML config parsing
│   ├── models.py               # Data models (TaxReturn, W2, 1099, etc.)
│   ├── document_parser.py      # PDF / image / spreadsheet parsing
│   ├── data_extractor.py       # Tax form data extraction (regex + logic)
│   ├── file_watcher.py         # Folder scanning & document categorization
│   ├── federal_tax.py          # Form 1040 calculation
│   ├── california_tax.py       # Form 540 calculation
│   ├── state_tax.py            # NY IT-201 and other state calculations
│   ├── schedule_a.py           # Itemized deductions
│   ├── schedule_e.py           # Rental property income
│   ├── form_filler.py          # PDF form filling (pypdf)
│   └── report_generator.py     # Tax summary report
├── pdf_templates/              # Blank IRS / CA PDF forms
├── Makefile                    # make install / make web / make demo
├── requirements.txt
└── README.md
```

---

## Testing

```bash
make test    # or: python test_tax_calculation.py
```

---

## Limitations

- OCR accuracy depends on document scan quality
- Complex situations (AMT, foreign income, multiple states) may need manual adjustment
- Supported states are California and New York; other states show withholding only

## Disclaimer

For educational and reference purposes only. Not a substitute for professional tax advice. Always verify results and consult a qualified tax professional for your situation.
