"""Field mapping for IRS Schedule A (Itemized Deductions).

Field names verified against 2025 IRS fillable PDF (sa.pdf).
Note: Schedule A uses 'form1[0]' prefix (not 'topmostSubform[0]').

2025 changes from 2024:
  - Lines 5a-5e restructured: combined income/sales tax into 5a,
    real estate moved to 5b, personal property to 5c, sum to 5d, cap to 5e
  - Line 8 adds 8d (reserved) and 8e (subtotal), shifting 9-17
  - Lines 11-14 (charity) shifted to f1_23-f1_26
  - Lines 15-17 shifted to f1_27-f1_30
"""

from typing import Dict
from ..models import TaxReturn
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


_P1 = "form1[0].Page1[0]"

# 2025 Schedule A field names from IRS fillable PDF.
# Verified via: python tools/discover_fields.py pdf_templates/2024/sa.pdf
FIELD_NAMES_2025 = {
    # Your name and SSN
    "name": f"{_P1}.f1_1[0]",
    "ssn": f"{_P1}.f1_2[0]",

    # Medical and Dental Expenses (Lines 1-4)
    "line1_medical": f"{_P1}.f1_3[0]",
    "line2_agi": f"{_P1}.Line2_ReadOrder[0].f1_4[0]",
    "line3_agi_pct": f"{_P1}.f1_5[0]",
    "line4_medical_deduction": f"{_P1}.f1_6[0]",

    # Taxes You Paid (Lines 5a-7)
    "line5a_state_local_tax": f"{_P1}.f1_7[0]",
    "line5a_check_income_tax": f"{_P1}.c1_1[0]",
    "line5b_real_estate_tax": f"{_P1}.f1_8[0]",
    "line5c_personal_property_tax": f"{_P1}.f1_9[0]",
    "line5d_total": f"{_P1}.f1_10[0]",
    "line5e_salt_limited": f"{_P1}.f1_11[0]",
    "line6_other_taxes_desc": f"{_P1}.f1_12[0]",
    "line6_other_taxes": f"{_P1}.f1_13[0]",
    "line7_total_taxes": f"{_P1}.f1_14[0]",

    # Interest You Paid (Lines 8-10)
    "line8_check": f"{_P1}.Line8_ReadOrder[0].c1_2[0]",
    "line8a_mortgage_interest_1098": f"{_P1}.f1_15[0]",
    "line8b_desc": f"{_P1}.Line8b_ReadOrder[0].f1_16[0]",
    "line8b_mortgage_interest_no1098": f"{_P1}.f1_17[0]",
    "line8c_points": f"{_P1}.f1_18[0]",
    # line8d = f1_19 (reserved for future use)
    "line8e_total_mortgage": f"{_P1}.f1_20[0]",
    "line9_investment_interest": f"{_P1}.f1_21[0]",
    "line10_total_interest": f"{_P1}.f1_22[0]",

    # Gifts to Charity (Lines 11-14)
    "line11_cash_contributions": f"{_P1}.f1_23[0]",
    "line12_noncash_contributions": f"{_P1}.f1_24[0]",
    "line13_carryover": f"{_P1}.f1_25[0]",
    "line14_total_charity": f"{_P1}.f1_26[0]",

    # Casualty and Theft Losses (Line 15)
    "line15_casualty": f"{_P1}.f1_27[0]",

    # Other Itemized Deductions (Line 16)
    "line16_other_desc": f"{_P1}.f1_28[0]",
    "line16_other": f"{_P1}.f1_29[0]",

    # Total Itemized Deductions (Line 17)
    "line17_total_itemized": f"{_P1}.f1_30[0]",

    # Line 18 checkbox (itemize even if less than standard deduction)
    "line18_limitation_check": f"{_P1}.Line18_ReadOrder[0].c1_3[0]",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2025,
    2025: FIELD_NAMES_2025,
}


@register("schedule_a", "sa.pdf")
def map_schedule_a(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Schedule A PDF field values."""
    fed = tax_return.federal_calculation
    sa = fed.schedule_a_result if fed else None
    if not sa or not sa.use_itemized:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2025)
    result = {}

    sched_a_data = tax_return.schedule_a_data

    # Name and SSN
    result[fields["name"]] = tax_return.taxpayer.name
    if tax_return.taxpayer.ssn:
        result[fields["ssn"]] = tax_return.taxpayer.ssn

    # Medical (Lines 1-4)
    if sched_a_data and sched_a_data.medical_expenses > 0:
        result[fields["line1_medical"]] = _dollars(sched_a_data.medical_expenses)
        result[fields["line2_agi"]] = _dollars(fed.adjusted_gross_income)
        result[fields["line3_agi_pct"]] = _dollars(fed.adjusted_gross_income * 0.075)
    result[fields["line4_medical_deduction"]] = _dollars(sa.medical_deduction)

    # Taxes paid (Lines 5a-7)
    if sched_a_data:
        result[fields["line5a_state_local_tax"]] = _dollars(sched_a_data.state_income_tax_paid)
        result[fields["line5a_check_income_tax"]] = "/1"  # Income tax (not sales tax)
        result[fields["line5b_real_estate_tax"]] = _dollars(sched_a_data.real_estate_taxes)
        vlf = sched_a_data.total_vehicle_license_fees
        if vlf > 0:
            result[fields["line5c_personal_property_tax"]] = _dollars(vlf)
        total_pre_cap = sched_a_data.state_income_tax_paid + sched_a_data.real_estate_taxes + vlf
        result[fields["line5d_total"]] = _dollars(total_pre_cap)
    result[fields["line5e_salt_limited"]] = _dollars(sa.salt_deduction)
    result[fields["line7_total_taxes"]] = _dollars(sa.salt_deduction)

    # Interest (Lines 8a, 8e, 10)
    result[fields["line8a_mortgage_interest_1098"]] = _dollars(sa.mortgage_interest_deduction)
    result[fields["line8e_total_mortgage"]] = _dollars(sa.mortgage_interest_deduction)
    result[fields["line10_total_interest"]] = _dollars(sa.mortgage_interest_deduction)

    # Charitable (Lines 11-14)
    if sched_a_data:
        if sched_a_data.cash_contributions > 0:
            result[fields["line11_cash_contributions"]] = _dollars(sched_a_data.cash_contributions)
        if sched_a_data.noncash_contributions > 0:
            result[fields["line12_noncash_contributions"]] = _dollars(sched_a_data.noncash_contributions)
    result[fields["line14_total_charity"]] = _dollars(sa.charitable_deduction)

    # Total (Line 17)
    result[fields["line17_total_itemized"]] = _dollars(sa.total_itemized)

    return result
