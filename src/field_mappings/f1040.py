"""Field mapping for IRS Form 1040 (U.S. Individual Income Tax Return).

Field names verified against 2025 IRS fillable PDF (f1040.pdf).
Run `python tools/discover_fields.py pdf_templates/2024/f1040.pdf` to verify.

NOTE: The template in pdf_templates/2024/ is actually a 2025 form.
"""

from typing import Dict
from ..models import TaxReturn, FilingStatus
from . import register


def _dollars(amount: float) -> str:
    """Format as whole dollars (IRS convention: round to nearest dollar)."""
    return str(round(amount))


# ---------------------------------------------------------------
# 2025 IRS Form 1040 field names from the fillable PDF.
#
# Page 1 header:
#   f1_01..f1_03  fiscal year fields (NOT names)
#   f1_04..f1_13  combat zone / deceased / other header
#   f1_14..f1_16  Your first name, last name, SSN
#   f1_17..f1_19  Spouse first name, last name, SSN
#   f1_20..f1_27  Address fields (inside Address_ReadOrder)
#   f1_28..f1_30  MFS / HOH / QSS name fields
#   f1_31..f1_46  Dependents table (column-based: 4 deps x 4 rows)
#
# Page 1 income:
#   f1_47  = Line 1a (wages)
#   f1_48..f1_55 = Lines 1b-1h sub-items
#   f1_56  = Line 1i (nontaxable combat pay)
#   f1_57  = Line 1z (total wages)
#   f1_58  = Line 2a (tax-exempt interest)    [left col, x=252]
#   f1_59  = Line 2b (taxable interest)       [right col, x=504]
#   f1_60  = Line 3a (qualified dividends)    [left]
#   f1_61  = Line 3b (ordinary dividends)     [right]
#   f1_62  = Line 4a (IRA distributions)      [left]
#   f1_63  = Line 4b (IRA taxable)            [right]
#   f1_64  = Line 4c (rollover/QCD check)
#   f1_65  = Line 5a (pensions gross)         [left]
#   f1_66  = Line 5b (pensions taxable)       [right]
#   f1_67  = Line 5c (rollover/PSO check)
#   f1_68  = Line 6a (social security)        [left]
#   f1_69  = Line 6b (SS taxable)             [right]
#   f1_70  = Line 7a (capital gain/loss)
#   f1_71  = Line 7b (Schedule D check text)
#   f1_72  = Line 8  (additional income, Sch 1)
#   f1_73  = Line 9  (total income)
#   f1_74  = Line 10 (adjustments, Sch 1)
#   f1_75  = Line 11a (AGI)
#
# Page 2:
#   f2_01  = Line 11b (AGI repeated)
#   f2_02  = Line 12e (deductions)
#   f2_03  = Line 13a (QBI deduction)
#   f2_04  = Line 13b (additional deductions)
#   f2_05  = Line 14  (total deductions)
#   f2_06  = Line 15  (taxable income)
#   f2_07  = Line 16  tax check text  [x=439]
#   f2_08  = Line 16  tax amount      [x=504]
#   f2_09  = Line 17  (Schedule 2, line 3)
#   f2_10  = Line 18  (add 16+17)
#   f2_11  = Line 19  (child tax credit, Sch 8812)
#   f2_12  = Line 20  (Schedule 3, line 8)
#   f2_13  = Line 21  (add 19+20)
#   f2_14  = Line 22  (18 minus 21)
#   f2_15  = Line 23  (other taxes, Sch 2 line 21)
#   f2_16  = Line 24  (total tax)
#   f2_17  = Line 25a (W-2 withheld)  [x=410]
#   f2_18  = Line 25b (1099 withheld) [x=410]
#   f2_19  = Line 25c (other withholding) [x=410]
#   f2_20  = Line 25d (total withheld)
#   f2_21  = Line 26  (estimated payments)
#   f2_22  = SSN for joint estimated payments
#   f2_23  = Line 27a (EIC)  [x=410]
#   f2_24..f2_27 = Lines 28-31
#   f2_28  = Line 32  (total other payments)
#   f2_29  = Line 33  (total payments)
#   f2_30  = Line 34  (overpaid)
#   f2_31  = Line 35a (refund)
#   f2_32  = Routing number
#   f2_33  = Account number
#   f2_34  = Line 36  (applied to next year)
#   f2_35  = Line 37  (amount owed)
# ---------------------------------------------------------------

_P1 = "topmostSubform[0].Page1[0]"
_P2 = "topmostSubform[0].Page2[0]"
_ADDR = f"{_P1}.Address_ReadOrder[0]"
_DEP = f"{_P1}.Table_Dependents[0]"

FIELD_NAMES_2025 = {
    # Filing status checkboxes
    "filing_status_single": f"{_P1}.c1_1[0]",
    "filing_status_mfj": f"{_P1}.c1_2[0]",
    "filing_status_mfs": f"{_P1}.c1_3[0]",
    "filing_status_hoh": f"{_P1}.c1_4[0]",

    # Name and SSN (f1_14..f1_19)
    "your_first_name": f"{_P1}.f1_14[0]",
    "your_last_name": f"{_P1}.f1_15[0]",
    "your_ssn": f"{_P1}.f1_16[0]",
    "spouse_first_name": f"{_P1}.f1_17[0]",
    "spouse_last_name": f"{_P1}.f1_18[0]",
    "spouse_ssn": f"{_P1}.f1_19[0]",

    # Address
    "address": f"{_ADDR}.f1_20[0]",
    "apt_no": f"{_ADDR}.f1_21[0]",
    "city": f"{_ADDR}.f1_22[0]",
    "state": f"{_ADDR}.f1_23[0]",
    "zip": f"{_ADDR}.f1_24[0]",

    # Main home in U.S. checkbox (c1_5)
    "main_home_us": f"{_P1}.c1_5[0]",

    # Digital assets Yes/No (c1_10)
    "digital_assets_yes": f"{_P1}.c1_10[0]",
    "digital_assets_no": f"{_P1}.c1_10[1]",

    # Dependents (2025 row layout: each row = one dependent with first, last, SSN, rel)
    # Row 1 (y=471): dep1
    "dep1_first": f"{_DEP}.Row1[0].f1_31[0]",
    "dep1_last": f"{_DEP}.Row1[0].f1_32[0]",
    "dep1_ssn": f"{_DEP}.Row1[0].f1_33[0]",
    "dep1_relationship": f"{_DEP}.Row1[0].f1_34[0]",
    # Row 2 (y=459): dep2
    "dep2_first": f"{_DEP}.Row2[0].f1_35[0]",
    "dep2_last": f"{_DEP}.Row2[0].f1_36[0]",
    "dep2_ssn": f"{_DEP}.Row2[0].f1_37[0]",
    "dep2_relationship": f"{_DEP}.Row2[0].f1_38[0]",
    # Row 3 (y=447): dep3
    "dep3_first": f"{_DEP}.Row3[0].f1_39[0]",
    "dep3_last": f"{_DEP}.Row3[0].f1_40[0]",
    "dep3_ssn": f"{_DEP}.Row3[0].f1_41[0]",
    "dep3_relationship": f"{_DEP}.Row3[0].f1_42[0]",
    # Row 4 (y=435): dep4
    "dep4_first": f"{_DEP}.Row4[0].f1_43[0]",
    "dep4_last": f"{_DEP}.Row4[0].f1_44[0]",
    "dep4_ssn": f"{_DEP}.Row4[0].f1_45[0]",
    "dep4_relationship": f"{_DEP}.Row4[0].f1_46[0]",

    # Dependent checkboxes: child tax credit (CTC) and credit for other dependents
    # Row 5 (y=425/413): CTC/ODC checkboxes per dependent column
    "dep1_ctc": f"{_DEP}.Row5[0].Dependent1[0].c1_12[0]",
    "dep1_odc": f"{_DEP}.Row5[0].Dependent1[0].c1_13[0]",
    "dep2_ctc": f"{_DEP}.Row5[0].Dependent2[0].c1_14[0]",
    "dep2_odc": f"{_DEP}.Row5[0].Dependent2[0].c1_15[0]",
    "dep3_ctc": f"{_DEP}.Row5[0].Dependent3[0].c1_16[0]",
    "dep3_odc": f"{_DEP}.Row5[0].Dependent3[0].c1_17[0]",
    "dep4_ctc": f"{_DEP}.Row5[0].Dependent4[0].c1_18[0]",
    "dep4_odc": f"{_DEP}.Row5[0].Dependent4[0].c1_19[0]",

    # Income lines
    "line1a_wages": f"{_P1}.f1_47[0]",
    "line1z_total_wages": f"{_P1}.f1_57[0]",
    "line2a_tax_exempt_interest": f"{_P1}.f1_58[0]",
    "line2b_taxable_interest": f"{_P1}.f1_59[0]",
    "line3a_qualified_dividends": f"{_P1}.f1_60[0]",
    "line3b_ordinary_dividends": f"{_P1}.f1_61[0]",
    "line4a_ira_distributions": f"{_P1}.f1_62[0]",
    "line4b_ira_taxable": f"{_P1}.f1_63[0]",
    "line5a_pensions": f"{_P1}.f1_65[0]",
    "line5b_pensions_taxable": f"{_P1}.f1_66[0]",
    "line6a_social_security": f"{_P1}.f1_68[0]",
    "line6b_ss_taxable": f"{_P1}.f1_69[0]",
    "line7_capital_gain_loss": f"{_P1}.f1_70[0]",
    "line8_other_income": f"{_P1}.f1_72[0]",
    "line9_total_income": f"{_P1}.f1_73[0]",
    "line10_adjustments": f"{_P1}.f1_74[0]",
    "line11a_agi": f"{_P1}.f1_75[0]",

    # Page 2 - Tax and credits
    "line11b_agi": f"{_P2}.f2_01[0]",
    "line12e_deductions": f"{_P2}.f2_02[0]",
    "line14_total_deductions": f"{_P2}.f2_05[0]",
    "line15_taxable_income": f"{_P2}.f2_06[0]",
    "line16_tax": f"{_P2}.f2_08[0]",
    "line17_schedule2": f"{_P2}.f2_09[0]",
    "line18_total_line16_17": f"{_P2}.f2_10[0]",
    "line19_child_tax_credit": f"{_P2}.f2_11[0]",
    "line21_total_credits": f"{_P2}.f2_13[0]",
    "line22_tax_minus_credits": f"{_P2}.f2_14[0]",
    "line23_other_taxes": f"{_P2}.f2_15[0]",
    "line24_total_tax": f"{_P2}.f2_16[0]",

    # Payments
    "line25a_w2_withheld": f"{_P2}.f2_17[0]",
    "line25b_1099_withheld": f"{_P2}.f2_18[0]",
    "line25c_other_withheld": f"{_P2}.f2_19[0]",
    "line25d_total_withheld": f"{_P2}.f2_20[0]",
    "line26_estimated_payments": f"{_P2}.f2_21[0]",
    "line33_total_payments": f"{_P2}.f2_29[0]",

    # Refund or amount owed
    "line34_overpaid": f"{_P2}.f2_30[0]",
    "line35a_refund": f"{_P2}.f2_31[0]",
    "line37_amount_owed": f"{_P2}.f2_35[0]",
}

# Field names may change between tax years
FIELD_NAMES = {
    2024: FIELD_NAMES_2025,
    2025: FIELD_NAMES_2025,
}


@register("f1040", "f1040.pdf")
def map_f1040(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to Form 1040 PDF field values."""
    fed = tax_return.federal_calculation
    if not fed:
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2025)
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

    # Name - split first/last from full name
    name_parts = tp.name.split()
    if name_parts:
        result[fields["your_first_name"]] = " ".join(name_parts[:-1]) if len(name_parts) > 1 else name_parts[0]
        result[fields["your_last_name"]] = name_parts[-1] if len(name_parts) > 1 else ""
    if tp.spouse_name:
        sp_parts = tp.spouse_name.split()
        if sp_parts:
            result[fields["spouse_first_name"]] = " ".join(sp_parts[:-1]) if len(sp_parts) > 1 else sp_parts[0]
            result[fields["spouse_last_name"]] = sp_parts[-1] if len(sp_parts) > 1 else ""

    if tp.ssn:
        result[fields["your_ssn"]] = tp.ssn.replace("-", "")
    if tp.spouse_ssn:
        result[fields["spouse_ssn"]] = tp.spouse_ssn.replace("-", "")

    # Address
    if tp.address_line1:
        result[fields["address"]] = tp.address_line1
    if tp.address_line2:
        parts = tp.address_line2.split(",")
        if len(parts) >= 2:
            result[fields["city"]] = parts[0].strip()
            state_zip = parts[-1].strip().split()
            if state_zip:
                result[fields["state"]] = state_zip[0]
            if len(state_zip) > 1:
                result[fields["zip"]] = state_zip[-1]

    # Main home in U.S. checkbox
    result[fields["main_home_us"]] = "/1"

    # Digital assets: default to "No"
    result[fields["digital_assets_no"]] = "/1"

    # Dependents
    dep_keys = [
        ("dep1_first", "dep1_last", "dep1_ssn", "dep1_relationship", "dep1_ctc", "dep1_odc"),
        ("dep2_first", "dep2_last", "dep2_ssn", "dep2_relationship", "dep2_ctc", "dep2_odc"),
        ("dep3_first", "dep3_last", "dep3_ssn", "dep3_relationship", "dep3_ctc", "dep3_odc"),
        ("dep4_first", "dep4_last", "dep4_ssn", "dep4_relationship", "dep4_ctc", "dep4_odc"),
    ]
    for i, dep in enumerate(tp.dependents[:4]):
        first_key, last_key, ssn_key, rel_key, ctc_key, odc_key = dep_keys[i]
        dep_name_parts = dep.name.split()
        if len(dep_name_parts) > 1:
            result[fields[first_key]] = " ".join(dep_name_parts[:-1])
            result[fields[last_key]] = dep_name_parts[-1]
        else:
            result[fields[first_key]] = dep.name
        if dep.ssn:
            result[fields[ssn_key]] = dep.ssn.strip().replace("-", "")
        result[fields[rel_key]] = dep.relationship
        # Check child tax credit (under 17) or credit for other dependents
        if dep.qualifies_for_child_tax_credit:
            result[fields[ctc_key]] = "/1"
        else:
            result[fields[odc_key]] = "/1"

    # Income lines
    result[fields["line1a_wages"]] = _dollars(inc.wages)
    result[fields["line1z_total_wages"]] = _dollars(inc.wages)
    # Line 2a: Tax-exempt interest (1099-INT Box 8)
    tax_exempt_interest = sum(
        getattr(f, "tax_exempt_interest", 0.0) for f in tax_return.form_1099_int
    )
    if tax_exempt_interest > 0:
        result[fields["line2a_tax_exempt_interest"]] = _dollars(tax_exempt_interest)
    result[fields["line2b_taxable_interest"]] = _dollars(inc.interest_income)
    result[fields["line3a_qualified_dividends"]] = _dollars(inc.qualified_dividends)
    result[fields["line3b_ordinary_dividends"]] = _dollars(inc.dividend_income)

    # IRA distributions (1099-R with IRA codes)
    # For now, map all 1099-R as pensions (line 5a/5b)
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
    result[fields["line10_adjustments"]] = _dollars(fed.adjustments)
    result[fields["line11a_agi"]] = _dollars(fed.adjusted_gross_income)

    # Page 2
    result[fields["line11b_agi"]] = _dollars(fed.adjusted_gross_income)
    result[fields["line12e_deductions"]] = _dollars(fed.deductions)
    result[fields["line14_total_deductions"]] = _dollars(fed.deductions)
    result[fields["line15_taxable_income"]] = _dollars(fed.taxable_income)

    # Line 16: Income tax only (from tax table / QD&CG worksheet)
    income_tax = fed.ordinary_income_tax + fed.qualified_dividend_ltcg_tax
    result[fields["line16_tax"]] = _dollars(income_tax)

    # Line 17: Schedule 2, Part I, line 3 (AMT + excess premium tax credit) — 0 for most
    # Line 18: Line 16 + Line 17
    result[fields["line18_total_line16_17"]] = _dollars(income_tax)

    # Credits (Lines 19-21)
    if fed.child_tax_credit > 0:
        result[fields["line19_child_tax_credit"]] = _dollars(fed.child_tax_credit)
    total_credits = fed.credits
    if total_credits > 0:
        result[fields["line21_total_credits"]] = _dollars(total_credits)

    # Line 22: Line 18 - Line 21 (not less than zero)
    tax_minus_credits = max(0, income_tax - total_credits)
    result[fields["line22_tax_minus_credits"]] = _dollars(tax_minus_credits)

    # Line 23: Schedule 2, Part II, line 21 (SE tax + Additional Medicare + NIIT)
    other_taxes = fed.self_employment_tax + fed.additional_medicare_tax + fed.niit
    if other_taxes > 0:
        result[fields["line23_other_taxes"]] = _dollars(other_taxes)

    # Line 24: Total tax = Line 22 + Line 23
    result[fields["line24_total_tax"]] = _dollars(tax_minus_credits + other_taxes)

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
