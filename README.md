# Tax Return Tool

A local, privacy-first tax calculator for **2024 and 2025**. Drop in your tax documents (W-2s, 1099s, 1098s, etc.) and it computes your Federal (Form 1040) and California (Form 540) taxes — entirely on your own machine.

> **100% offline.** No documents, numbers, or personal data ever leave your computer.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/yingxuan/tax-return-tool.git
cd tax-return-tool
make install          # installs Tesseract OCR + Python packages

# 2. Launch
make web              # opens at http://localhost:5000
```

**Windows:** `make install` handles Python packages automatically. For Tesseract, [download and run this installer](https://github.com/UB-Mannheim/tesseract/wiki), then run `make web`.

No documents? Try the demo: `make demo`

---

## How It Works

1. You provide a folder of tax documents (PDFs, images, spreadsheets)
2. The tool OCRs and parses them — extracting wages, interest, dividends, mortgage interest, property taxes, etc.
3. It runs the full tax calculation and shows your refund or amount owed
4. Anything it can't find in your documents (charitable contributions, estimated payments, etc.) it asks you for explicitly

---

## Using the Web UI

```bash
make web    # or: python -m src.ui_app
```

Open **http://localhost:5000**. The UI walks you through three steps:

**Step 1 — Your Profile**
Filing status, dependents, capital loss carryovers, mortgage balance, rental properties. You can also upload a saved `tax_profile.yaml` here to pre-fill everything.

**Step 2 — Tax Documents**
Drag and drop files, or type a folder path. The tool scans all PDFs, images, and spreadsheets it finds.

**Step 3 — Missing Info**
After the first run, the tool flags anything it couldn't extract from your documents (e.g. charitable donations, estimated payments) and asks for those values specifically.

---

## Using the CLI

```bash
# Run with a config file (best for repeat use)
python -m src.main --config path/to/tax_profile.yaml

# Point at a folder of documents directly
python -m src.main --local-folder path/to/tax/docs

# Demo mode — no documents needed
python -m src.main --demo
```

---

## Configuration File (optional)

A config file is not required for the Web UI. It's useful if you use the CLI or want to save your settings for reuse.

Copy [`config/tax_profile.sample.yaml`](config/tax_profile.sample.yaml) to `config/tax_profile.yaml` (gitignored) and fill in your values:

```yaml
tax_year: 2025

taxpayer:
  name: "Jane & John Doe"
  filing_status: married_jointly   # single | married_jointly | married_separately | head_of_household
  age: 42
  is_ca_resident: true
  dependents:
    - name: "Alice Doe"
      age: 8
      relationship: "daughter"

# Folder containing your W-2s, 1099s, 1098s, etc.
document_folder: "/path/to/tax/documents"

# Capital loss carryover from prior year (up to $3,000/year deductible)
short_term_loss_carryover: 0
long_term_loss_carryover: 0

# Outstanding mortgage balance — used to prorate interest when balance > $750K
# (Set to 0 if your balance is under $750K)
personal_mortgage_balance: 0

# Cash donations not captured in your documents
charitable_contributions: 0

# Estimated tax payments made during the year
federal_estimated_payments: 0
ca_estimated_payments: 0

# Rental property (Schedule E)
# Insurance, property tax, and management fees are auto-extracted from documents
rental_properties:
  - address: "123 Rental St, Anytown, CA 90210"
    property_type: "Single Family"
    purchase_price: 900000
    purchase_date: "2018-06-01"
    land_value: 180000      # non-depreciable portion of purchase price
    rental_income: 36000    # annual gross rent
    other_expenses: 0       # gardening, phone, misc — if not in documents
```

---

## Supported Documents

| Form | What it covers | Fields extracted |
|------|---------------|-----------------|
| **W-2** | Wages & withholding | Wages, federal/state withheld, 401k |
| **1099-INT** | Interest income | Box 1 interest, US Treasury interest |
| **1099-DIV** | Dividends | Ordinary, qualified, capital gains |
| **1099-B / Composite** | Brokerage sales | Proceeds, cost basis, gain/loss |
| **1099-NEC** | Self-employment | Nonemployee compensation |
| **1099-R** | Retirement distributions | Gross distribution, taxable amount |
| **1098** | Mortgage interest | Interest paid, property taxes, points |
| **Property tax bill** | Real estate taxes | Amount, property address |
| **Home insurance** | Insurance premium | Annual premium |
| **Vehicle registration** | CA deductible fees | License fee amount |
| **PM statement** | Rental expenses | Management fees, repairs |

**File formats:** PDF (text or scanned), JPEG, PNG, TIFF, BMP, CSV, Excel (.xlsx/.xls)

---

## Tax Calculations Covered

**Federal (Form 1040)**
- Standard vs. itemized deductions (Schedule A)
- SALT cap ($10,000), mortgage interest with debt-limit proration, charitable contributions
- Qualified dividend / long-term capital gain preferential rates
- Child tax credit, additional Medicare tax (0.9%), net investment income tax (3.8%)
- Capital loss carryover (up to $3,000/year)
- Rental income/loss (Schedule E), 27.5-year depreciation, passive activity loss limits

**California (Form 540)**
- CA tax brackets + Mental Health Services Tax (1% over $1M)
- No SALT cap, $1M mortgage debt limit, CA-specific deductions
- Renter's credit

**PDF form output:** fills and saves the actual IRS 1040 and CA 540 PDF forms.

---

## Installation Details

### Python packages
```bash
pip install -r requirements.txt
```

### Tesseract OCR
Required for image files and scanned PDFs.

| Platform | Command |
|----------|---------|
| macOS | `brew install tesseract` |
| Linux (Debian/Ubuntu) | `sudo apt-get install tesseract-ocr` |
| Windows | [Download installer](https://github.com/UB-Mannheim/tesseract/wiki) |

`make install` handles macOS and Linux automatically.

### Virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
make install
```

---

## Project Structure

```
tax-return-tool/
├── config/
│   └── tax_profile.sample.yaml   # Annotated example config
├── src/
│   ├── main.py                   # CLI entry point
│   ├── ui_app.py                 # Web UI (Flask)
│   ├── document_parser.py        # PDF / image / spreadsheet parsing
│   ├── data_extractor.py         # Form data extraction (regex + logic)
│   ├── federal_tax.py            # Form 1040 calculation
│   ├── schedule_a.py             # Itemized deductions
│   ├── schedule_e.py             # Rental property income
│   ├── california_tax.py         # Form 540 calculation
│   ├── form_filler.py            # PDF form filling
│   └── report_generator.py       # Tax summary output
├── pdf_templates/                # Blank IRS / CA PDF forms
├── Makefile
├── requirements.txt
└── test_tax_calculation.py
```

---

## Limitations

- OCR accuracy depends on document scan quality — text-based PDFs work best
- Complex situations (AMT, foreign income, multi-state) may need manual adjustment
- Full state tax calculation for California only; other states show withholding totals

## Disclaimer

For reference purposes only. Not a substitute for professional tax advice. Always verify results with a qualified tax professional.
