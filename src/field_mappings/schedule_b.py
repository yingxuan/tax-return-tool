"""Field mapping for IRS Schedule B (Interest and Ordinary Dividends).

Field names verified against 2024 IRS fillable PDF (f1040sb.pdf).
"""

from typing import Dict
from ..models import TaxReturn
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


# 2024 Schedule B actual field names from IRS fillable PDF.
# Verified via: python tools/discover_fields.py pdf_templates/2024/sb.pdf
#
# Part I (Interest): payer/amount pairs in f1_01..f1_33
# Part II (Dividends): payer/amount pairs in f1_18..f1_33 area
# The field numbering is sequential.
FIELD_NAMES_2024 = {
    # Part I - Interest payers (name + amount pairs)
    "int_payer_1": "topmostSubform[0].Page1[0].f1_01[0]",
    "int_amount_1": "topmostSubform[0].Page1[0].f1_02[0]",
    "int_payer_2": "topmostSubform[0].Page1[0].f1_03[0]",
    "int_amount_2": "topmostSubform[0].Page1[0].f1_04[0]",
    "int_payer_3": "topmostSubform[0].Page1[0].f1_05[0]",
    "int_amount_3": "topmostSubform[0].Page1[0].f1_06[0]",
    "int_payer_4": "topmostSubform[0].Page1[0].f1_07[0]",
    "int_amount_4": "topmostSubform[0].Page1[0].f1_08[0]",
    "int_payer_5": "topmostSubform[0].Page1[0].f1_09[0]",
    "int_amount_5": "topmostSubform[0].Page1[0].f1_10[0]",
    "int_payer_6": "topmostSubform[0].Page1[0].f1_11[0]",
    "int_amount_6": "topmostSubform[0].Page1[0].f1_12[0]",
    "int_payer_7": "topmostSubform[0].Page1[0].f1_13[0]",
    "int_amount_7": "topmostSubform[0].Page1[0].f1_14[0]",

    # Line 1 subtotal (read-order field)
    "line1_subtotal": "topmostSubform[0].Page1[0].Line1_ReadOrder[0].f1_03[0]",
    # Line 4 total interest
    "line4_total_interest": "topmostSubform[0].Page1[0].ReadOrderControl[0].f1_34[0]",

    # Part II - Dividend payers (name + amount pairs)
    "div_payer_1": "topmostSubform[0].Page1[0].f1_15[0]",
    "div_amount_1": "topmostSubform[0].Page1[0].f1_16[0]",
    "div_payer_2": "topmostSubform[0].Page1[0].f1_17[0]",
    "div_amount_2": "topmostSubform[0].Page1[0].f1_18[0]",
    "div_payer_3": "topmostSubform[0].Page1[0].f1_19[0]",
    "div_amount_3": "topmostSubform[0].Page1[0].f1_20[0]",
    "div_payer_4": "topmostSubform[0].Page1[0].f1_21[0]",
    "div_amount_4": "topmostSubform[0].Page1[0].f1_22[0]",
    "div_payer_5": "topmostSubform[0].Page1[0].f1_23[0]",
    "div_amount_5": "topmostSubform[0].Page1[0].f1_24[0]",
    "div_payer_6": "topmostSubform[0].Page1[0].f1_25[0]",
    "div_amount_6": "topmostSubform[0].Page1[0].f1_26[0]",
    "div_payer_7": "topmostSubform[0].Page1[0].f1_27[0]",
    "div_amount_7": "topmostSubform[0].Page1[0].f1_28[0]",

    # Line 6 total dividends
    "line6_total_dividends": "topmostSubform[0].Page1[0].f1_33[0]",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2024,
    2025: FIELD_NAMES_2024,
}


@register("schedule_b", "sb.pdf")
def map_schedule_b(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Schedule B PDF field values."""
    inc = tax_return.income
    # Schedule B required if interest or dividends > $1,500
    if inc.interest_income <= 1500 and inc.dividend_income <= 1500:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2024)
    result = {}

    # Part I - Interest payers
    int_forms = tax_return.form_1099_int
    for i, form in enumerate(int_forms[:7], 1):
        payer_key = f"int_payer_{i}"
        amount_key = f"int_amount_{i}"
        if payer_key in fields:
            result[fields[payer_key]] = form.payer_name
            result[fields[amount_key]] = _dollars(form.interest_income)

    result[fields["line4_total_interest"]] = _dollars(inc.interest_income)

    # Part II - Dividend payers
    div_forms = tax_return.form_1099_div
    for i, form in enumerate(div_forms[:7], 1):
        payer_key = f"div_payer_{i}"
        amount_key = f"div_amount_{i}"
        if payer_key in fields:
            result[fields[payer_key]] = form.payer_name
            result[fields[amount_key]] = _dollars(form.ordinary_dividends)

    result[fields["line6_total_dividends"]] = _dollars(inc.dividend_income)

    return result
