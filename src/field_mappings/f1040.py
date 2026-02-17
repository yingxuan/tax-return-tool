"""Field mapping for IRS Form 1040 (U.S. Individual Income Tax Return).

Field names verified against 2024 IRS fillable PDF (f1040.pdf).
Run `python tools/discover_fields.py pdf_templates/2024/f1040.pdf` to verify.
"""

from typing import Dict
from ..models import TaxReturn, FilingStatus
from . import register


def _dollars(amount: float) -> str:
    """Format as whole dollars (IRS convention: round to nearest dollar)."""
    return str(round(amount))


# 2024 IRS Form 1040 actual field names from the fillable PDF.
# Verified via: python tools/discover_fields.py pdf_templates/2024/f1040.pdf
#
# Page 1 header fields: f1_01..f1_19 (name, SSN, etc.)
# Address: Address_ReadOrder[0].f1_20..f1_27
# Filing status checkboxes: c1_1[0]=Single, c1_2[0]=MFJ, c1_3[0]=MFS, c1_4[0]=HOH, c1_5[0]=QSS
# Dependents table: Table_Dependents[0].Row1..Row4
# Income lines: f1_47..f1_75 (Lines 1a through 15)
# Page 2: f2_01..f2_51 (tax computation, credits, payments, refund)
FIELD_NAMES_2024 = {
    # Filing status checkboxes
    "filing_status_single": "topmostSubform[0].Page1[0].c1_1[0]",
    "filing_status_mfj": "topmostSubform[0].Page1[0].c1_2[0]",
    "filing_status_mfs": "topmostSubform[0].Page1[0].c1_3[0]",
    "filing_status_hoh": "topmostSubform[0].Page1[0].c1_4[0]",

    # Name and SSN (Page 1 header)
    "your_first_name": "topmostSubform[0].Page1[0].f1_01[0]",
    "your_last_name": "topmostSubform[0].Page1[0].f1_02[0]",
    "your_ssn": "topmostSubform[0].Page1[0].f1_03[0]",
    "spouse_first_name": "topmostSubform[0].Page1[0].f1_04[0]",
    "spouse_last_name": "topmostSubform[0].Page1[0].f1_05[0]",
    "spouse_ssn": "topmostSubform[0].Page1[0].f1_06[0]",

    # Address (Address_ReadOrder subform)
    "address": "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_20[0]",
    "apt_no": "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_21[0]",
    "city": "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_22[0]",
    "state": "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_23[0]",
    "zip": "topmostSubform[0].Page1[0].Address_ReadOrder[0].f1_24[0]",

    # Dependents (Row1 = first dependent)
    "dep1_name": "topmostSubform[0].Page1[0].Table_Dependents[0].Row1[0].f1_31[0]",
    "dep1_ssn": "topmostSubform[0].Page1[0].Table_Dependents[0].Row1[0].f1_32[0]",
    "dep1_relationship": "topmostSubform[0].Page1[0].Table_Dependents[0].Row1[0].f1_33[0]",
    "dep2_name": "topmostSubform[0].Page1[0].Table_Dependents[0].Row2[0].f1_35[0]",
    "dep2_ssn": "topmostSubform[0].Page1[0].Table_Dependents[0].Row2[0].f1_36[0]",
    "dep2_relationship": "topmostSubform[0].Page1[0].Table_Dependents[0].Row2[0].f1_37[0]",

    # Income lines (f1_47 = Line 1a wages, incrementing through Line 15)
    # Lines 1a-1z: Various wage components
    "line1a_wages": "topmostSubform[0].Page1[0].f1_47[0]",      # Line 1a: W-2 wages
    "line1z_total_wages": "topmostSubform[0].Page1[0].f1_56[0]", # Line 1z: Total
    "line2a_tax_exempt_interest": "topmostSubform[0].Page1[0].f1_57[0]",
    "line2b_taxable_interest": "topmostSubform[0].Page1[0].f1_58[0]",
    "line3a_qualified_dividends": "topmostSubform[0].Page1[0].f1_59[0]",
    "line3b_ordinary_dividends": "topmostSubform[0].Page1[0].f1_60[0]",
    "line4a_ira_distributions": "topmostSubform[0].Page1[0].f1_61[0]",
    "line4b_ira_taxable": "topmostSubform[0].Page1[0].f1_62[0]",
    "line5a_pensions": "topmostSubform[0].Page1[0].f1_63[0]",
    "line5b_pensions_taxable": "topmostSubform[0].Page1[0].f1_64[0]",
    "line6a_social_security": "topmostSubform[0].Page1[0].f1_65[0]",
    "line6b_ss_taxable": "topmostSubform[0].Page1[0].f1_66[0]",
    "line7_capital_gain_loss": "topmostSubform[0].Page1[0].f1_67[0]",
    "line8_other_income": "topmostSubform[0].Page1[0].f1_68[0]",
    "line9_total_income": "topmostSubform[0].Page1[0].f1_69[0]",
    "line10a_adjustments": "topmostSubform[0].Page1[0].f1_70[0]",
    "line10c_total_adjustments": "topmostSubform[0].Page1[0].f1_72[0]",
    "line11_agi": "topmostSubform[0].Page1[0].f1_73[0]",
    "line12_deductions": "topmostSubform[0].Page1[0].f1_74[0]",
    "line15_taxable_income": "topmostSubform[0].Page1[0].f1_75[0]",

    # Page 2 - Tax and credits
    "line16_tax": "topmostSubform[0].Page2[0].f2_01[0]",
    "line17_schedule2": "topmostSubform[0].Page2[0].f2_02[0]",
    "line18_total_line16_17": "topmostSubform[0].Page2[0].f2_03[0]",
    "line19_child_tax_credit": "topmostSubform[0].Page2[0].f2_04[0]",
    "line21_other_credits": "topmostSubform[0].Page2[0].f2_05[0]",
    "line22_total_credits": "topmostSubform[0].Page2[0].f2_06[0]",
    "line23_tax_minus_credits": "topmostSubform[0].Page2[0].f2_07[0]",
    "line24_other_taxes": "topmostSubform[0].Page2[0].f2_08[0]",
    "line25_total_tax": "topmostSubform[0].Page2[0].f2_09[0]",

    # Payments
    "line25a_w2_withheld": "topmostSubform[0].Page2[0].f2_10[0]",
    "line25b_1099_withheld": "topmostSubform[0].Page2[0].f2_11[0]",
    "line25c_other_withheld": "topmostSubform[0].Page2[0].f2_12[0]",
    "line25d_total_withheld": "topmostSubform[0].Page2[0].f2_13[0]",
    "line26_estimated_payments": "topmostSubform[0].Page2[0].f2_14[0]",
    "line33_total_payments": "topmostSubform[0].Page2[0].f2_19[0]",

    # Refund or amount owed
    "line34_overpaid": "topmostSubform[0].Page2[0].f2_20[0]",
    "line35a_refund": "topmostSubform[0].Page2[0].f2_21[0]",
    "line37_amount_owed": "topmostSubform[0].Page2[0].f2_23[0]",
}

# Field names may change between tax years
FIELD_NAMES = {
    2024: FIELD_NAMES_2024,
    2025: FIELD_NAMES_2024,  # Assume same until 2025 forms are released
}


@register("f1040", "f1040.pdf")
def map_f1040(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Form 1040 PDF field values."""
    fed = tax_return.federal_calculation
    if not fed:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2024)
    result = {}

    tp = tax_return.taxpayer
    inc = tax_return.income

    # Filing status checkbox
    status_field_map = {
        FilingStatus.SINGLE: "filing_status_single",
        FilingStatus.MARRIED_FILING_JOINTLY: "filing_status_mfj",
        FilingStatus.MARRIED_FILING_SEPARATELY: "filing_status_mfs",
        FilingStatus.HEAD_OF_HOUSEHOLD: "filing_status_hoh",
    }
    status_key = status_field_map.get(tp.filing_status)
    if status_key and status_key in fields:
        result[fields[status_key]] = "/1"

    # Name - split first/last from combined name
    name_parts = tp.name.split()
    if name_parts:
        if "&" in tp.name:
            ampersand_idx = name_parts.index("&")
            result[fields["your_first_name"]] = " ".join(name_parts[:ampersand_idx])
            result[fields["your_last_name"]] = name_parts[-1]
            if ampersand_idx + 1 < len(name_parts) - 1:
                result[fields["spouse_first_name"]] = " ".join(name_parts[ampersand_idx + 1:-1])
                result[fields["spouse_last_name"]] = name_parts[-1]
        else:
            result[fields["your_first_name"]] = " ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0]
            result[fields["your_last_name"]] = name_parts[-1] if len(name_parts) > 1 else ""

    if tp.ssn:
        result[fields["your_ssn"]] = tp.ssn
    if tp.spouse_ssn:
        result[fields["spouse_ssn"]] = tp.spouse_ssn

    # Address
    if tp.address_line1:
        result[fields["address"]] = tp.address_line1
    if tp.address_line2:
        # Parse city, state, zip
        parts = tp.address_line2.split(",")
        if len(parts) >= 2:
            result[fields["city"]] = parts[0].strip()
            state_zip = parts[-1].strip().split()
            if state_zip:
                result[fields["state"]] = state_zip[0]
            if len(state_zip) > 1:
                result[fields["zip"]] = state_zip[-1]

    # Dependents
    for i, dep in enumerate(tp.dependents[:2], 1):
        result[fields[f"dep{i}_name"]] = dep.name
        if dep.ssn:
            result[fields[f"dep{i}_ssn"]] = dep.ssn
        result[fields[f"dep{i}_relationship"]] = dep.relationship

    # Income lines
    result[fields["line1a_wages"]] = _dollars(inc.wages)
    result[fields["line1z_total_wages"]] = _dollars(inc.wages)
    result[fields["line2b_taxable_interest"]] = _dollars(inc.interest_income)
    result[fields["line3a_qualified_dividends"]] = _dollars(inc.qualified_dividends)
    result[fields["line3b_ordinary_dividends"]] = _dollars(inc.dividend_income)

    # Retirement income (1099-R)
    if inc.retirement_income > 0:
        total_gross = sum(f.gross_distribution for f in tax_return.form_1099_r)
        result[fields["line5a_pensions"]] = _dollars(total_gross)
        result[fields["line5b_pensions_taxable"]] = _dollars(inc.retirement_income)

    # Capital gains
    if inc.capital_gains != 0:
        result[fields["line7_capital_gain_loss"]] = _dollars(inc.capital_gains)

    # Other income (self-employment + rental + other)
    other = inc.self_employment_income + inc.other_income + inc.rental_income
    if other != 0:
        result[fields["line8_other_income"]] = _dollars(other)

    # Totals
    result[fields["line9_total_income"]] = _dollars(fed.gross_income)
    result[fields["line10a_adjustments"]] = _dollars(fed.adjustments)
    result[fields["line10c_total_adjustments"]] = _dollars(fed.adjustments)
    result[fields["line11_agi"]] = _dollars(fed.adjusted_gross_income)
    result[fields["line12_deductions"]] = _dollars(fed.deductions)
    result[fields["line15_taxable_income"]] = _dollars(fed.taxable_income)

    # Tax
    result[fields["line16_tax"]] = _dollars(fed.tax_before_credits)

    # Other taxes (SE + Additional Medicare + NIIT) -> Schedule 2
    other_taxes = fed.self_employment_tax + fed.additional_medicare_tax + fed.niit
    if other_taxes > 0:
        result[fields["line17_schedule2"]] = _dollars(other_taxes)
        result[fields["line18_total_line16_17"]] = _dollars(fed.tax_before_credits + other_taxes)
    else:
        result[fields["line18_total_line16_17"]] = _dollars(fed.tax_before_credits)

    # Credits
    if fed.child_tax_credit > 0:
        result[fields["line19_child_tax_credit"]] = _dollars(fed.child_tax_credit)
    result[fields["line22_total_credits"]] = _dollars(fed.credits)

    tax_minus_credits = fed.tax_before_credits + other_taxes - fed.credits
    result[fields["line23_tax_minus_credits"]] = _dollars(max(0, tax_minus_credits))
    result[fields["line25_total_tax"]] = _dollars(fed.tax_after_credits)

    # Payments
    w2_withheld = sum(w.federal_withheld for w in tax_return.w2_forms)
    other_withheld = tax_return.total_federal_withheld - w2_withheld
    result[fields["line25a_w2_withheld"]] = _dollars(w2_withheld)
    if other_withheld > 0:
        result[fields["line25b_1099_withheld"]] = _dollars(other_withheld)
    result[fields["line25d_total_withheld"]] = _dollars(tax_return.total_federal_withheld)

    if fed.estimated_payments > 0:
        result[fields["line26_estimated_payments"]] = _dollars(fed.estimated_payments)

    total_payments = fed.total_payments
    result[fields["line33_total_payments"]] = _dollars(total_payments)

    # Refund or owed
    refund_or_owed = fed.refund_or_owed
    if refund_or_owed > 0:
        result[fields["line34_overpaid"]] = _dollars(refund_or_owed)
        result[fields["line35a_refund"]] = _dollars(refund_or_owed)
    elif refund_or_owed < 0:
        result[fields["line37_amount_owed"]] = _dollars(abs(refund_or_owed))

    return result
