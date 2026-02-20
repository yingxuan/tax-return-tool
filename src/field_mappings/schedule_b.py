"""Field mapping for IRS Schedule B (Interest and Ordinary Dividends).

Field names verified against 2025 IRS fillable PDF (sb.pdf).

2025 changes from 2024:
  - f1_01/f1_02 are now name/SSN header fields (new)
  - Interest payers shifted: start at f1_03 (14 rows, f1_03-f1_30)
  - Note: f1_03 is under Line1_ReadOrder subform, all others under Page1
  - Dividend payers shifted: start at f1_36 (14 rows, f1_36-f1_63)
  - Line totals: Line 1 subtotal=f1_31, Line 4=f1_35, Line 6=f1_64
"""

from typing import Dict
from ..models import TaxReturn
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


_P1 = "topmostSubform[0].Page1[0]"

# 2025 Schedule B actual field names from IRS fillable PDF.
# Verified via: python tools/discover_fields.py pdf_templates/2024/sb.pdf
FIELD_NAMES_2025 = {
    # Header (new in 2025)
    "name": f"{_P1}.f1_01[0]",
    "ssn": f"{_P1}.f1_02[0]",

    # Part I - Interest payers (name + amount pairs)
    # Note: payer 1 name is under Line1_ReadOrder subform
    "int_payer_1": f"{_P1}.Line1_ReadOrder[0].f1_03[0]",
    "int_amount_1": f"{_P1}.f1_04[0]",
    "int_payer_2": f"{_P1}.f1_05[0]",
    "int_amount_2": f"{_P1}.f1_06[0]",
    "int_payer_3": f"{_P1}.f1_07[0]",
    "int_amount_3": f"{_P1}.f1_08[0]",
    "int_payer_4": f"{_P1}.f1_09[0]",
    "int_amount_4": f"{_P1}.f1_10[0]",
    "int_payer_5": f"{_P1}.f1_11[0]",
    "int_amount_5": f"{_P1}.f1_12[0]",
    "int_payer_6": f"{_P1}.f1_13[0]",
    "int_amount_6": f"{_P1}.f1_14[0]",
    "int_payer_7": f"{_P1}.f1_15[0]",
    "int_amount_7": f"{_P1}.f1_16[0]",

    # Line 1 subtotal
    "line1_subtotal": f"{_P1}.f1_31[0]",
    # Line 4 total interest
    "line4_total_interest": f"{_P1}.f1_35[0]",

    # Part II - Dividend payers (name + amount pairs)
    "div_payer_1": f"{_P1}.f1_36[0]",
    "div_amount_1": f"{_P1}.f1_37[0]",
    "div_payer_2": f"{_P1}.f1_38[0]",
    "div_amount_2": f"{_P1}.f1_39[0]",
    "div_payer_3": f"{_P1}.f1_40[0]",
    "div_amount_3": f"{_P1}.f1_41[0]",
    "div_payer_4": f"{_P1}.f1_42[0]",
    "div_amount_4": f"{_P1}.f1_43[0]",
    "div_payer_5": f"{_P1}.f1_44[0]",
    "div_amount_5": f"{_P1}.f1_45[0]",
    "div_payer_6": f"{_P1}.f1_46[0]",
    "div_amount_6": f"{_P1}.f1_47[0]",
    "div_payer_7": f"{_P1}.f1_48[0]",
    "div_amount_7": f"{_P1}.f1_49[0]",

    # Line 6 total dividends
    "line6_total_dividends": f"{_P1}.f1_64[0]",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2025,
    2025: FIELD_NAMES_2025,
}


@register("schedule_b", "sb.pdf")
def map_schedule_b(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Schedule B PDF field values."""
    inc = tax_return.income
    # Schedule B required if interest or dividends > $1,500
    if inc.interest_income <= 1500 and inc.dividend_income <= 1500:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2025)
    result = {}

    # Name and SSN (IRS: no dashes)
    result[fields["name"]] = tax_return.taxpayer.name
    if tax_return.taxpayer.ssn:
        result[fields["ssn"]] = tax_return.taxpayer.ssn.replace("-", "")

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
