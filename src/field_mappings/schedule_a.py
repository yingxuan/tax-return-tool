"""Field mapping for IRS Schedule A (Itemized Deductions).

Field names verified against 2024 IRS fillable PDF (f1040sa.pdf).
Note: Schedule A uses 'form1[0]' prefix (not 'topmostSubform[0]').
"""

from typing import Dict
from ..models import TaxReturn
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


# 2024 Schedule A actual field names from IRS fillable PDF.
# Verified via: python tools/discover_fields.py pdf_templates/2024/sa.pdf
FIELD_NAMES_2024 = {
    # Your name and SSN
    "name": "form1[0].Page1[0].f1_1[0]",
    "ssn": "form1[0].Page1[0].f1_2[0]",

    # Medical and Dental Expenses
    "line1_medical": "form1[0].Page1[0].f1_3[0]",
    "line2_agi": "form1[0].Page1[0].f1_4[0]",
    "line3_agi_pct": "form1[0].Page1[0].f1_5[0]",
    "line4_medical_deduction": "form1[0].Page1[0].f1_6[0]",

    # Taxes You Paid
    "line5a_state_income_tax": "form1[0].Page1[0].f1_7[0]",
    "line5b_state_sales_tax": "form1[0].Page1[0].f1_8[0]",
    "line5c_check_income_tax": "form1[0].Page1[0].c1_1[0]",
    "line5d_real_estate_tax": "form1[0].Page1[0].f1_9[0]",
    "line5e_personal_property_tax": "form1[0].Page1[0].f1_10[0]",
    "line5f_total_add": "form1[0].Page1[0].f1_11[0]",
    "line5g_salt_limited": "form1[0].Page1[0].f1_12[0]",
    "line6_other_taxes": "form1[0].Page1[0].f1_13[0]",
    "line7_total_taxes": "form1[0].Page1[0].f1_14[0]",

    # Interest You Paid
    "line8a_mortgage_interest_1098": "form1[0].Page1[0].f1_15[0]",
    "line8b_mortgage_interest_no1098": "form1[0].Page1[0].Line8_ReadOrder[0].f1_16[0]",
    "line8c_points": "form1[0].Page1[0].f1_17[0]",
    "line9_investment_interest": "form1[0].Page1[0].f1_18[0]",
    "line10_total_interest": "form1[0].Page1[0].f1_19[0]",

    # Gifts to Charity
    "line11_cash_contributions": "form1[0].Page1[0].f1_20[0]",
    "line12_noncash_contributions": "form1[0].Page1[0].f1_21[0]",
    "line13_carryover": "form1[0].Page1[0].f1_22[0]",
    "line14_total_charity": "form1[0].Page1[0].f1_23[0]",

    # Casualty and Other
    "line15_casualty": "form1[0].Page1[0].f1_24[0]",
    "line16_other": "form1[0].Page1[0].f1_25[0]",
    "line17_total_itemized": "form1[0].Page1[0].f1_26[0]",

    # Line 18 checkbox (limitation applies)
    "line18_limitation_check": "form1[0].Page1[0].Line18_ReadOrder[0].c1_3[0]",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2024,
    2025: FIELD_NAMES_2024,
}


@register("schedule_a", "sa.pdf")
def map_schedule_a(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Schedule A PDF field values."""
    fed = tax_return.federal_calculation
    sa = fed.schedule_a_result if fed else None
    if not sa or not sa.use_itemized:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2024)
    result = {}

    sched_a_data = tax_return.schedule_a_data

    # Name and SSN
    result[fields["name"]] = tax_return.taxpayer.name
    if tax_return.taxpayer.ssn:
        result[fields["ssn"]] = tax_return.taxpayer.ssn

    # Medical
    if sched_a_data and sched_a_data.medical_expenses > 0:
        result[fields["line1_medical"]] = _dollars(sched_a_data.medical_expenses)
        result[fields["line2_agi"]] = _dollars(fed.adjusted_gross_income)
        result[fields["line3_agi_pct"]] = _dollars(fed.adjusted_gross_income * 0.075)
    result[fields["line4_medical_deduction"]] = _dollars(sa.medical_deduction)

    # Taxes paid
    if sched_a_data:
        result[fields["line5a_state_income_tax"]] = _dollars(sched_a_data.state_income_tax_paid)
        result[fields["line5c_check_income_tax"]] = "/1"  # Income tax (not sales tax)
        result[fields["line5d_real_estate_tax"]] = _dollars(sched_a_data.real_estate_taxes)
        vlf = sched_a_data.total_vehicle_license_fees
        if vlf > 0:
            result[fields["line5e_personal_property_tax"]] = _dollars(vlf)
        total_pre_cap = sched_a_data.state_income_tax_paid + sched_a_data.real_estate_taxes + vlf
        result[fields["line5f_total_add"]] = _dollars(total_pre_cap)
    result[fields["line7_total_taxes"]] = _dollars(sa.salt_deduction)

    # Interest
    result[fields["line8a_mortgage_interest_1098"]] = _dollars(sa.mortgage_interest_deduction)
    result[fields["line10_total_interest"]] = _dollars(sa.mortgage_interest_deduction)

    # Charitable
    if sched_a_data:
        if sched_a_data.cash_contributions > 0:
            result[fields["line11_cash_contributions"]] = _dollars(sched_a_data.cash_contributions)
        if sched_a_data.noncash_contributions > 0:
            result[fields["line12_noncash_contributions"]] = _dollars(sched_a_data.noncash_contributions)
    result[fields["line14_total_charity"]] = _dollars(sa.charitable_deduction)

    # Total
    result[fields["line17_total_itemized"]] = _dollars(sa.total_itemized)

    return result
