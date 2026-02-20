"""Field mapping for IRS Schedule E (Supplemental Income and Loss).

Supports up to 3 rental properties per page (IRS limit).
Field names verified against 2024 IRS fillable PDF (f1040se.pdf).
"""

from typing import Dict
from ..models import TaxReturn, FilingStatus
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


# 2024 Schedule E actual field names from IRS fillable PDF.
# Each expense line has 3 columns (A/B/C) for up to 3 properties.
# Verified via: python tools/discover_fields.py pdf_templates/2024/se.pdf
FIELD_NAMES_2024 = {
    # Header
    "name": "topmostSubform[0].Page1[0].f1_1[0]",
    "ssn": "topmostSubform[0].Page1[0].f1_2[0]",

    # Property addresses (Line 1a - RowA/B/C)
    "prop_a_address": "topmostSubform[0].Page1[0].Table_Line1a[0].RowA[0].f1_3[0]",
    "prop_b_address": "topmostSubform[0].Page1[0].Table_Line1a[0].RowB[0].f1_4[0]",
    "prop_c_address": "topmostSubform[0].Page1[0].Table_Line1a[0].RowC[0].f1_5[0]",

    # Property type codes (Line 1b)
    "prop_a_type": "topmostSubform[0].Page1[0].Table_Line1b[0].RowA[0].f1_6[0]",
    "prop_b_type": "topmostSubform[0].Page1[0].Table_Line1b[0].RowB[0].f1_7[0]",
    "prop_c_type": "topmostSubform[0].Page1[0].Table_Line1b[0].RowC[0].f1_8[0]",

    # Fair rental days / personal use days (Line 2)
    "prop_a_rental_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowA[0].f1_9[0]",
    "prop_a_personal_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowA[0].f1_10[0]",
    "prop_b_rental_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowB[0].f1_11[0]",
    "prop_b_personal_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowB[0].f1_12[0]",
    "prop_c_rental_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowC[0].f1_13[0]",
    "prop_c_personal_days": "topmostSubform[0].Page1[0].Table_Line2[0].RowC[0].f1_14[0]",

    # Line 3 - Rents received
    "prop_a_rents": "topmostSubform[0].Page1[0].Table_Income[0].Line3[0].f1_16[0]",
    "prop_b_rents": "topmostSubform[0].Page1[0].Table_Income[0].Line3[0].f1_17[0]",
    "prop_c_rents": "topmostSubform[0].Page1[0].Table_Income[0].Line3[0].f1_18[0]",

    # Expenses - Line 5: Advertising
    "prop_a_advertising": "topmostSubform[0].Page1[0].Table_Expenses[0].Line5[0].f1_22[0]",
    "prop_b_advertising": "topmostSubform[0].Page1[0].Table_Expenses[0].Line5[0].f1_23[0]",
    "prop_c_advertising": "topmostSubform[0].Page1[0].Table_Expenses[0].Line5[0].f1_24[0]",
    # Line 6 - Auto and travel
    "prop_a_auto": "topmostSubform[0].Page1[0].Table_Expenses[0].Line6[0].f1_25[0]",
    "prop_b_auto": "topmostSubform[0].Page1[0].Table_Expenses[0].Line6[0].f1_26[0]",
    "prop_c_auto": "topmostSubform[0].Page1[0].Table_Expenses[0].Line6[0].f1_27[0]",
    # Line 7 - Cleaning and maintenance
    "prop_a_cleaning": "topmostSubform[0].Page1[0].Table_Expenses[0].Line7[0].f1_28[0]",
    "prop_b_cleaning": "topmostSubform[0].Page1[0].Table_Expenses[0].Line7[0].f1_29[0]",
    "prop_c_cleaning": "topmostSubform[0].Page1[0].Table_Expenses[0].Line7[0].f1_30[0]",
    # Line 8 - Commissions
    "prop_a_commissions": "topmostSubform[0].Page1[0].Table_Expenses[0].Line8[0].f1_31[0]",
    "prop_b_commissions": "topmostSubform[0].Page1[0].Table_Expenses[0].Line8[0].f1_32[0]",
    "prop_c_commissions": "topmostSubform[0].Page1[0].Table_Expenses[0].Line8[0].f1_33[0]",
    # Line 9 - Insurance
    "prop_a_insurance": "topmostSubform[0].Page1[0].Table_Expenses[0].Line9[0].f1_34[0]",
    "prop_b_insurance": "topmostSubform[0].Page1[0].Table_Expenses[0].Line9[0].f1_35[0]",
    "prop_c_insurance": "topmostSubform[0].Page1[0].Table_Expenses[0].Line9[0].f1_36[0]",
    # Line 10 - Legal and professional fees
    "prop_a_legal": "topmostSubform[0].Page1[0].Table_Expenses[0].Line10[0].f1_37[0]",
    "prop_b_legal": "topmostSubform[0].Page1[0].Table_Expenses[0].Line10[0].f1_38[0]",
    "prop_c_legal": "topmostSubform[0].Page1[0].Table_Expenses[0].Line10[0].f1_39[0]",
    # Line 11 - Management fees
    "prop_a_management": "topmostSubform[0].Page1[0].Table_Expenses[0].Line11[0].f1_40[0]",
    "prop_b_management": "topmostSubform[0].Page1[0].Table_Expenses[0].Line11[0].f1_41[0]",
    "prop_c_management": "topmostSubform[0].Page1[0].Table_Expenses[0].Line11[0].f1_42[0]",
    # Line 12 - Mortgage interest paid to financial institutions
    "prop_a_mortgage_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line12[0].f1_43[0]",
    "prop_b_mortgage_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line12[0].f1_44[0]",
    "prop_c_mortgage_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line12[0].f1_45[0]",
    # Line 13 - Other interest
    "prop_a_other_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line13[0].f1_46[0]",
    "prop_b_other_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line13[0].f1_47[0]",
    "prop_c_other_interest": "topmostSubform[0].Page1[0].Table_Expenses[0].Line13[0].f1_48[0]",
    # Line 14 - Repairs
    "prop_a_repairs": "topmostSubform[0].Page1[0].Table_Expenses[0].Line14[0].f1_49[0]",
    "prop_b_repairs": "topmostSubform[0].Page1[0].Table_Expenses[0].Line14[0].f1_50[0]",
    "prop_c_repairs": "topmostSubform[0].Page1[0].Table_Expenses[0].Line14[0].f1_51[0]",
    # Line 15 - Supplies
    "prop_a_supplies": "topmostSubform[0].Page1[0].Table_Expenses[0].Line15[0].f1_52[0]",
    "prop_b_supplies": "topmostSubform[0].Page1[0].Table_Expenses[0].Line15[0].f1_53[0]",
    "prop_c_supplies": "topmostSubform[0].Page1[0].Table_Expenses[0].Line15[0].f1_54[0]",
    # Line 16 - Taxes
    "prop_a_taxes": "topmostSubform[0].Page1[0].Table_Expenses[0].Line16[0].f1_55[0]",
    "prop_b_taxes": "topmostSubform[0].Page1[0].Table_Expenses[0].Line16[0].f1_56[0]",
    "prop_c_taxes": "topmostSubform[0].Page1[0].Table_Expenses[0].Line16[0].f1_57[0]",
    # Line 17 - Utilities
    "prop_a_utilities": "topmostSubform[0].Page1[0].Table_Expenses[0].Line17[0].f1_58[0]",
    "prop_b_utilities": "topmostSubform[0].Page1[0].Table_Expenses[0].Line17[0].f1_59[0]",
    "prop_c_utilities": "topmostSubform[0].Page1[0].Table_Expenses[0].Line17[0].f1_60[0]",
    # Line 18 - Depreciation expense or depletion
    "prop_a_depreciation": "topmostSubform[0].Page1[0].Table_Expenses[0].Line18[0].f1_61[0]",
    "prop_b_depreciation": "topmostSubform[0].Page1[0].Table_Expenses[0].Line18[0].f1_62[0]",
    "prop_c_depreciation": "topmostSubform[0].Page1[0].Table_Expenses[0].Line18[0].f1_63[0]",
    # Line 19 - Other (includes description field f1_67)
    "prop_a_other": "topmostSubform[0].Page1[0].Table_Expenses[0].Line19[0].f1_64[0]",
    "prop_b_other": "topmostSubform[0].Page1[0].Table_Expenses[0].Line19[0].f1_65[0]",
    "prop_c_other": "topmostSubform[0].Page1[0].Table_Expenses[0].Line19[0].f1_66[0]",
    # Line 20 - Total expenses
    "prop_a_total_expenses": "topmostSubform[0].Page1[0].Table_Expenses[0].Line20[0].f1_68[0]",
    "prop_b_total_expenses": "topmostSubform[0].Page1[0].Table_Expenses[0].Line20[0].f1_69[0]",
    "prop_c_total_expenses": "topmostSubform[0].Page1[0].Table_Expenses[0].Line20[0].f1_70[0]",
    # Line 21 - Net income/loss per property
    "prop_a_net": "topmostSubform[0].Page1[0].Table_Expenses[0].Line21[0].f1_71[0]",
    "prop_b_net": "topmostSubform[0].Page1[0].Table_Expenses[0].Line21[0].f1_72[0]",
    "prop_c_net": "topmostSubform[0].Page1[0].Table_Expenses[0].Line21[0].f1_73[0]",

    # Line 26 - Total rental real estate and royalty income/loss
    "line26_total": "topmostSubform[0].Page2[0].Line42_ReadOrder[0].f2_79[0]",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2024,
    2025: FIELD_NAMES_2024,
}

# Property type code mapping
PROPERTY_TYPE_CODES = {
    "Single Family": "1",
    "Multi-Family": "2",
    "Vacation/Short-Term": "3",
    "Commercial": "4",
    "Land": "5",
    "Royalties": "6",
    "Self-Rental": "7",
    "Other": "8",
}


@register("schedule_e", "se.pdf")
def map_schedule_e(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Schedule E PDF field values."""
    if not tax_return.rental_properties:
        return {}

    summary = tax_return.schedule_e_summary
    if not summary:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2024)
    result = {}

    # Header (joint name for MFJ; SSN without dashes per IRS convention)
    tp = tax_return.taxpayer
    if tp.filing_status == FilingStatus.MARRIED_FILING_JOINTLY and tp.spouse_name:
        result[fields["name"]] = f"{tp.name} & {tp.spouse_name}"
    else:
        result[fields["name"]] = tp.name
    if tp.ssn:
        result[fields["ssn"]] = tp.ssn.replace("-", "")

    # Map up to 3 properties (A, B, C columns)
    col_keys = ["a", "b", "c"]

    for idx, (prop, sched_result) in enumerate(
        zip(tax_return.rental_properties[:3], summary.properties[:3])
    ):
        col = col_keys[idx]

        # Address and type
        result[fields[f"prop_{col}_address"]] = prop.address
        type_code = PROPERTY_TYPE_CODES.get(prop.property_type, "1")
        result[fields[f"prop_{col}_type"]] = type_code

        # Days
        result[fields[f"prop_{col}_rental_days"]] = str(prop.days_rented)
        result[fields[f"prop_{col}_personal_days"]] = str(prop.personal_use_days)

        # Rents received
        result[fields[f"prop_{col}_rents"]] = _dollars(prop.rental_income)

        # Expenses
        if prop.advertising > 0:
            result[fields[f"prop_{col}_advertising"]] = _dollars(prop.advertising)
        if prop.auto_and_travel > 0:
            result[fields[f"prop_{col}_auto"]] = _dollars(prop.auto_and_travel)
        if prop.cleaning_and_maintenance > 0:
            result[fields[f"prop_{col}_cleaning"]] = _dollars(prop.cleaning_and_maintenance)
        if prop.commissions > 0:
            result[fields[f"prop_{col}_commissions"]] = _dollars(prop.commissions)
        if prop.insurance > 0:
            result[fields[f"prop_{col}_insurance"]] = _dollars(prop.insurance)
        if prop.legal_and_professional > 0:
            result[fields[f"prop_{col}_legal"]] = _dollars(prop.legal_and_professional)
        if prop.management_fees > 0:
            result[fields[f"prop_{col}_management"]] = _dollars(prop.management_fees)
        if prop.mortgage_interest > 0:
            result[fields[f"prop_{col}_mortgage_interest"]] = _dollars(prop.mortgage_interest)
        if prop.repairs > 0:
            result[fields[f"prop_{col}_repairs"]] = _dollars(prop.repairs)
        if prop.supplies > 0:
            result[fields[f"prop_{col}_supplies"]] = _dollars(prop.supplies)
        if prop.property_tax > 0:
            result[fields[f"prop_{col}_taxes"]] = _dollars(prop.property_tax)
        if prop.utilities > 0:
            result[fields[f"prop_{col}_utilities"]] = _dollars(prop.utilities)

        # Depreciation from computed result
        result[fields[f"prop_{col}_depreciation"]] = _dollars(sched_result.depreciation)

        if prop.other_expenses > 0:
            result[fields[f"prop_{col}_other"]] = _dollars(prop.other_expenses)

        # Totals
        total_exp = sched_result.total_expenses + sched_result.depreciation
        result[fields[f"prop_{col}_total_expenses"]] = _dollars(total_exp)
        result[fields[f"prop_{col}_net"]] = _dollars(sched_result.net_income)

    # Total rental income/loss
    result[fields["line26_total"]] = _dollars(summary.total_net_rental_income)

    return result
