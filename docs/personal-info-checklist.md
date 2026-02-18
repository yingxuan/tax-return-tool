# 2025 Tax Forms - Personal Information Checklist

This document lists all personal information needed to fill out the 2025 tax forms
(Form 1040, Schedule A, Schedule B, Schedule E, CA Form 540) using this tool.

---

## 1. Taxpayer Identity & Filing Info

| Field | Used By | Config YAML Key | Status |
|-------|---------|-----------------|--------|
| Full name (taxpayer) | 1040, CA 540 | `taxpayer.name` | Supported |
| Full name (spouse, if MFJ) | 1040, CA 540 | Embedded in name with `&` | Supported |
| SSN (taxpayer) | 1040, Sch A, CA 540 | `taxpayer.ssn` | **Not in config** |
| SSN (spouse) | 1040, CA 540 | — | **Not in config** |
| Filing status | 1040, CA 540 | `taxpayer.filing_status` | Supported |
| Age | Internal (credits) | `taxpayer.age` | Supported |
| Street address | 1040, CA 540 | `taxpayer.address_line1` | Supported |
| City, State, ZIP | 1040, CA 540 | `taxpayer.address_line2` | Supported |
| State of residence | CA 540 | `state_of_residence` | Supported |
| Is renter (CA) | CA 540 | `taxpayer.is_renter` | Supported |

### Gap: SSN
SSNs are not currently in the YAML config (intentionally, for security). They could be:
- Added to config (risk: SSN in plaintext file)
- Prompted at runtime via `--interactive` flag
- Left blank for user to hand-fill on printed PDF

**Recommendation**: Add optional `ssn` and `spouse_ssn` fields to config, or add a
`--ssn` / `--spouse-ssn` CLI arg. Warn if config file has SSNs and is not gitignored.

---

## 2. Dependents

| Field | Used By | Config YAML Key | Status |
|-------|---------|-----------------|--------|
| Dependent name | 1040 | `taxpayer.dependents[].name` | Supported |
| Dependent age | Internal (CTC) | `taxpayer.dependents[].age` | Supported |
| Dependent relationship | 1040 | `taxpayer.dependents[].relationship` | Supported |
| Dependent SSN | 1040 | `taxpayer.dependents[].ssn` | **Not in config** |

### Gap: Dependent SSN
Same security concern as taxpayer SSN. Currently the `Dependent` model has an `ssn` field
but it's not parsed from config YAML.

---

## 3. Income Documents (Auto-Extracted from PDFs)

These are extracted from scanned/PDF documents in the `document_folder`. No manual entry
needed if documents are provided.

| Document | Fields Extracted | Forms Filled |
|----------|-----------------|--------------|
| **W-2** | Employer name, wages (Box 1), federal withheld (Box 2), SS wages (Box 3), SS tax (Box 4), Medicare wages (Box 5), Medicare tax (Box 6), state wages (Box 16), state withheld (Box 17) | 1040 Lines 1a, 25a |
| **1099-INT** | Payer name, interest (Box 1), US Treasury interest (Box 3), federal withheld (Box 4) | 1040 Line 2b, Sch B |
| **1099-DIV** | Payer name, ordinary dividends (Box 1a), qualified dividends (Box 1b), capital gain distributions (Box 2a), federal withheld (Box 4) | 1040 Lines 3a/3b, Sch B |
| **1099-R** | Payer name, gross distribution (Box 1), taxable amount (Box 2a), federal withheld (Box 4), distribution code (Box 7), state withheld (Box 12) | 1040 Lines 5a/5b |
| **1099-B** | Broker name, proceeds, cost basis, gain/loss, wash sale adjustments | 1040 Line 7 |
| **1099-MISC** | Payer name, rents (Box 1), other income (Box 3), federal withheld | 1040 Line 8 |
| **1099-NEC** | Payer name, nonemployee compensation (Box 1), federal withheld | 1040 Line 8 |
| **1099-G** | State tax refund (Box 2), unemployment (Box 1) | 1040 |
| **1098** | Lender name, mortgage interest (Box 1), points (Box 6), property taxes (Box 10) | Sch A Lines 8a/5d |
| **1098-T** | Institution name, tuition billed (Box 1), scholarships (Box 5) | (education credits) |

---

## 4. Manual Config Entries (Not Auto-Extractable)

These values must be entered in `config/tax_profile.yaml` because they cannot be
reliably extracted from standard tax documents.

### 4a. Schedule A - Itemized Deductions

| Field | Config YAML Key | Notes |
|-------|-----------------|-------|
| Charitable contributions (cash) | `charitable_contributions` | Receipts not auto-parsed |
| Primary home property tax | `primary_property_tax` | Overrides 1098 Box 10 if set |
| Primary home APN | `primary_home_apn` | For matching multi-parcel receipts |
| Personal mortgage balance | `personal_mortgage_balance` | For $750K/$1M debt limit proration |
| CA misc deductions | `ca_misc_deductions` | Advisory fees, tax prep (CA-only) |
| Medical expenses | — | **Not in config** (see gaps below) |
| Noncash charitable contributions | — | **Not in config** |

### 4b. Schedule E - Rental Properties

| Field | Config YAML Key | Notes |
|-------|-----------------|-------|
| Property address | `rental_properties[].address` | Required |
| Property type | `rental_properties[].property_type` | Default: Single Family |
| Purchase price | `rental_properties[].purchase_price` | For depreciation |
| Purchase date | `rental_properties[].purchase_date` | YYYY-MM-DD |
| Land value | `rental_properties[].land_value` | Not depreciable |
| Gross rental income | `rental_properties[].rental_income` | Annual rent collected |
| Insurance | `rental_properties[].insurance` | Annual premium |
| Property tax | `rental_properties[].property_tax` | Annual amount |
| Other expenses | `rental_properties[].other_expenses` | Gardening, phone, etc. |
| Days rented | `rental_properties[].days_rented` | Default: 365 |
| Personal use days | `rental_properties[].personal_use_days` | Default: 0 |
| Rental 1098 keywords | `rental_1098_keywords` | Match rental mortgage 1098s |

### 4c. Adjustments & Overrides

| Field | Config YAML Key | Notes |
|-------|-----------------|-------|
| US Treasury interest | `us_treasury_interest` | State-exempt; sole source of truth |
| Capital loss carryover (ST) | `short_term_loss_carryover` | From prior-year Schedule D |
| Capital loss carryover (LT) | `long_term_loss_carryover` | From prior-year Schedule D |
| PAL carryover | `pal_carryover` | Prior-year passive loss (Form 8582) |
| Federal estimated payments | `federal_estimated_payments` | Total of Q1-Q4 payments |
| CA estimated payments | `ca_estimated_payments` | Total of Q1-Q4 payments |
| Federal withholding adjustment | `federal_withheld_adjustment` | Correct extraction errors |
| Other income | `other_income` | Jury duty, 1099-MISC Box 3, etc. |
| Qualified dividends override | `qualified_dividends` | Override if extraction is wrong |
| Ordinary dividends override | `ordinary_dividends` | Override if extraction is wrong |

---

## 5. Identified Gaps (Not Yet Supported)

These fields appear on the tax forms but are not yet capturable through the tool:

### High Priority

| Field | Form Line | Needed For | Proposed Solution |
|-------|-----------|------------|-------------------|
| **Taxpayer SSN** | 1040 header, Sch A | All forms | Add `ssn` to config or CLI arg |
| **Spouse SSN** | 1040 header, CA 540 | MFJ filers | Add `spouse_ssn` to config or CLI arg |
| **Dependent SSN** | 1040 dependents table | CTC claims | Parse from `dependents[].ssn` in config |
| **Medical expenses** | Sch A Line 1 | Itemizers with high medical | Add `medical_expenses` to config |
| **Noncash contributions** | Sch A Line 12 | Itemizers donating goods | Add `noncash_contributions` to config |
| **Spouse name** (separate field) | 1040, CA 540 | MFJ name clarity | Currently parsed from `&` in name; could add explicit `spouse_name` |

### Medium Priority

| Field | Form Line | Needed For | Proposed Solution |
|-------|-----------|------------|-------------------|
| **Bank routing/account** | 1040 Line 35b-d | Direct deposit refund | Add to config (sensitive) |
| **Occupation** | 1040 signature area | Form completion | Add to config |
| **Phone number** | 1040 signature area | Form completion | Add to config |
| **Filing date** | 1040 signature | Form completion | Auto-fill with current date |
| **CA county** | CA 540 | CA filing | Could derive from ZIP |

### Low Priority (Rare Scenarios)

| Field | Notes |
|-------|-------|
| Foreign accounts (FBAR/FinCEN) | Schedule B Part III |
| Energy credits | Form 5695 |
| Education credits detail | Form 8863 |
| Alternative Minimum Tax | Form 6251 |
| Casualty losses | Schedule A Line 15 |

---

## 6. Implementation Plan

### Phase 1: SSN Support
1. Add `ssn` and `spouse_ssn` to `TaxProfileConfig` and YAML parsing
2. Add `ssn` to `DependentConfig` and parse from config
3. Wire through to `TaxpayerInfo` and `Dependent` models
4. Update field mappings to populate SSN fields on all forms
5. Add security warning if config contains SSNs

### Phase 2: Missing Schedule A Fields
1. Add `medical_expenses` to config (already in `ScheduleAData` model)
2. Add `noncash_contributions` to config (already in `ScheduleAData` model)
3. Wire config values into `ScheduleAData` during tax return assembly

### Phase 3: Form Completion Fields
1. Add `occupation`, `spouse_occupation`, `phone`, `email` to config
2. Add bank routing/account fields (for direct deposit)
3. Map to 1040 signature area and refund direct deposit section
4. Add field mappings for these new fields

### Phase 4: CA-Specific
1. Add CA county field (or derive from ZIP lookup)
2. Map to CA 540 if needed

---

## 7. Quick Reference: Minimum Info Needed

For a **basic return** (W-2 income, standard deduction, no rentals):

```yaml
taxpayer:
  name: "John Doe"
  ssn: "123-45-6789"          # Phase 1
  filing_status: single
  age: 35
  address_line1: "123 Main St"
  address_line2: "San Jose, CA 95123"

tax_year: 2025
state_of_residence: CA
document_folder: "./documents/2025"
```

For a **full return** (itemized, rentals, investments, MFJ):

```yaml
taxpayer:
  name: "John & Jane Doe"
  ssn: "123-45-6789"          # Phase 1
  spouse_ssn: "987-65-4321"   # Phase 1
  filing_status: married_filing_jointly
  age: 40
  is_renter: false
  address_line1: "456 Oak Ave"
  address_line2: "Sunnyvale, CA 94086"
  dependents:
    - name: "Jimmy Doe"
      age: 8
      relationship: "son"
      ssn: "111-22-3333"      # Phase 1

tax_year: 2025
state_of_residence: CA
document_folder: "./documents/2025"

# Carryovers from prior year
short_term_loss_carryover: 0
long_term_loss_carryover: 1500
pal_carryover: 5000

# Manual entries
charitable_contributions: 3000
noncash_contributions: 500       # Phase 2
medical_expenses: 12000          # Phase 2
us_treasury_interest: 200
personal_mortgage_balance: 650000
primary_property_tax: 8500

# Estimated payments
federal_estimated_payments: 5000
ca_estimated_payments: 2000

# Rental
rental_1098_keywords: ["rental lender"]
rental_properties:
  - address: "789 Elm St, San Jose, CA 95112"
    purchase_price: 850000
    purchase_date: "2020-06-15"
    land_value: 250000
    rental_income: 36000
    insurance: 1800
    property_tax: 6000
    other_expenses: 500
```
