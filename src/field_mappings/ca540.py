"""Field mapping for California Form 540 (CA Resident Income Tax Return).

Field names verified against 2025 FTB fillable PDF (ca540.pdf).
FTB uses flat naming: 540_form_XYYY where X=page, YYY=field sequence.

Run `python tools/discover_fields.py pdf_templates/2024/ca540.pdf` to verify.
"""

from typing import Dict
from ..models import TaxReturn, FilingStatus
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


# ------------------------------------------------------------------
# 2025 CA Form 540 field names, verified against the actual PDF.
#
# Page 1 (1xxx): header, address, DOB, principal residence,
#                filing status (radio 1036 RB), exemptions lines 7-9
# Page 2 (2xxx): dependents (line 10), exemption amount (line 11),
#                taxable income (lines 12-19), tax (lines 31-35),
#                special credits (lines 40, 43-44)
# Page 3 (3xxx): credits cont. (lines 45-48), other taxes (61-64),
#                payments (71-78), use tax (91), ISR (92),
#                overpaid/tax due (93-97)
# Page 4 (4xxx): overpaid cont. (98-100), voluntary contributions
# ------------------------------------------------------------------
FIELD_NAMES_2025 = {
    # Page 1 - Header
    "county_header": "540_form_1002",
    "your_first_name": "540_form_1003",
    "your_mi": "540_form_1004",
    "your_last_name": "540_form_1005",
    "your_suffix": "540_form_1006",
    "your_ssn": "540_form_1007",
    "spouse_first_name": "540_form_1008",
    "spouse_mi": "540_form_1009",
    "spouse_last_name": "540_form_1010",
    "spouse_suffix": "540_form_1011",
    "spouse_ssn": "540_form_1012",

    # Page 1 - Additional info / mailing address
    "additional_info": "540_form_1013",
    "pba_code": "540_form_1014",
    "address": "540_form_1015",
    "apt_no": "540_form_1016",
    "pmb": "540_form_1017",
    "city": "540_form_1018",
    "state": "540_form_1019",
    "zip": "540_form_1020",

    # Page 1 - Foreign address (only used for foreign filers)
    "foreign_country": "540_form_1021",
    "foreign_province": "540_form_1022",
    "foreign_postal_code": "540_form_1023",

    # Page 1 - DOB
    "your_dob": "540_form_1024",
    "spouse_dob": "540_form_1025",

    # Page 1 - Prior name (if name changed)
    "your_prior_name": "540_form_1026",
    "spouse_prior_name": "540_form_1027",

    # Page 1 - Principal Residence section
    "county_at_filing": "540_form_1028",  # "Enter your county at time of filing"
    "same_as_mailing_cb": "540_form_1029 CB",  # Check if principal = mailing
    "principal_street": "540_form_1030",  # Principal residence street (if different)
    "principal_apt": "540_form_1031",  # Principal residence apt/ste
    "principal_city": "540_form_1032",  # Principal residence city
    "principal_state": "540_form_1033",  # Principal residence state
    "principal_zip": "540_form_1034",  # Principal residence ZIP

    # Page 1 - Filing status (radio button group)
    "filing_status": "540_form_1036 RB",

    # Page 1 - MFS spouse name field (line 3 area)
    "mfs_spouse_name": "540_form_1037",

    # Page 1 - Exemptions (lines 7-9)
    "line7_personal_num": "540_form_1041",
    "line7_personal_amt": "540_form_1042",
    "line8_blind_num": "540_form_1043",
    "line8_blind_amt": "540_form_1044",
    "line9_senior_num": "540_form_1045",
    "line9_senior_amt": "540_form_1046",

    # Page 2 - Header (name/SSN repeated on each page)
    "p2_name": "540_form_2001",
    "p2_ssn": "540_form_2002",

    # Page 2 - Dependents (line 10)
    "dep1_first": "540_form_2003",
    "dep1_last": "540_form_2004",
    "dep1_ssn": "540_form_2005",
    "dep1_relationship": "540_form_2006",
    "dep2_first": "540_form_2007",
    "dep2_last": "540_form_2008",
    "dep2_ssn": "540_form_2009",
    "dep2_relationship": "540_form_2010",
    "dep3_first": "540_form_2011",
    "dep3_last": "540_form_2012",
    "dep3_ssn": "540_form_2013",
    "dep3_relationship": "540_form_2014",
    "line10_dep_num": "540_form_2015",
    "line10_dep_amt": "540_form_2016",

    # Line 11: total exemption amount
    "line11_exemption_amount": "540_form_2017",

    # Taxable Income section (lines 12-19)
    "line12_state_wages": "540_form_2018",
    "line13_federal_agi": "540_form_2019",
    "line14_ca_subtractions": "540_form_2020",
    "line15_subtotal": "540_form_2021",
    "line16_ca_additions": "540_form_2022",
    "line17_ca_agi": "540_form_2023",
    "line18_deductions": "540_form_2024",
    "line19_taxable_income": "540_form_2025",

    # Tax section (lines 31-35)
    "line31_tax": "540_form_2030",
    "line32_exemption_credits": "540_form_2031",
    "line33_subtotal": "540_form_2032",
    # 2033/2034 CB = checkboxes for line 34 tax source
    "line35_total": "540_form_2036",

    # Special Credits
    "line40_child_care_credit": "540_form_2037",

    # Page 3 - Header
    "p3_name": "540_form_2001",  # same field name, different page
    "p3_ssn": "540_form_2002",

    # Credits continuation (lines 45-48)
    "line46_renters_credit": "540_form_3004",
    "line47_total_credits": "540_form_3005",
    "line48_net_tax": "540_form_3006",

    # Other taxes (lines 61-64)
    "line61_amt": "540_form_3007",
    "line62_mental_health_tax": "540_form_3008",
    "line63_other_taxes": "540_form_3009",
    "line64_total_tax": "540_form_3010",

    # Payments (lines 71-78)
    "line71_ca_withheld": "540_form_3011",
    "line72_estimated_payments": "540_form_3012",
    "line78_total_payments": "540_form_3018",

    # Overpaid/Tax Due (lines 93-97)
    "line93_payments_balance": "540_form_3023",
    "line95_after_isr": "540_form_3025",
    "line97_overpaid": "540_form_3027",

    # Page 4 - Overpaid continuation
    "line99_refund": "540_form_4004",
    "line100_amount_owed": "540_form_4005",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2025,  # FTB 2024 form may differ; verify
    2025: FIELD_NAMES_2025,
}

# Filing status radio button values (from PDF widget /AP /N inspection).
# The PDF uses the full descriptive label as the appearance state name.
_FILING_STATUS_RADIO = {
    FilingStatus.SINGLE: "/1 . Single.",
    FilingStatus.MARRIED_FILING_JOINTLY: "/2 . Married/R D P filing jointly (even if only one spouse / R D P had income). See instructions.",
    FilingStatus.MARRIED_FILING_SEPARATELY: "/3 . Married or R D P filing separately.",
    FilingStatus.HEAD_OF_HOUSEHOLD: "/4 . Head of household (with qualifying person). See instructions.",
}


@register("ca540", "ca540.pdf")
def map_ca540(tax_return: TaxReturn) -> Dict[str, str]:
    """Map TaxReturn data to CA Form 540 PDF field values."""
    ca = tax_return.state_calculation
    if not ca or ca.jurisdiction != "California":
        return {}

    year = tax_return.tax_year
    fields = FIELD_NAMES.get(year, FIELD_NAMES_2025)
    result = {}

    tp = tax_return.taxpayer
    fed = tax_return.federal_calculation

    # --- Page 1: Header ---

    # Your name
    name_parts = tp.name.split()
    if name_parts:
        if len(name_parts) > 1:
            result[fields["your_first_name"]] = " ".join(name_parts[:-1])
            result[fields["your_last_name"]] = name_parts[-1]
        else:
            result[fields["your_first_name"]] = name_parts[0]

    # Your SSN (normalized: no dashes for e-file consistency)
    if tp.ssn:
        result[fields["your_ssn"]] = tp.ssn.replace("-", "")

    # Spouse name & SSN
    if tp.spouse_name:
        sp_parts = tp.spouse_name.split()
        if sp_parts:
            if len(sp_parts) > 1:
                result[fields["spouse_first_name"]] = " ".join(sp_parts[:-1])
                result[fields["spouse_last_name"]] = sp_parts[-1]
            else:
                result[fields["spouse_first_name"]] = sp_parts[0]
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

    # County (header and principal residence "at time of filing")
    if tp.county:
        result[fields["county_header"]] = tp.county
        result[fields["county_at_filing"]] = tp.county

    # DOB
    if tp.date_of_birth:
        result[fields["your_dob"]] = tp.date_of_birth
    if tp.spouse_dob:
        result[fields["spouse_dob"]] = tp.spouse_dob

    # Principal residence: check "same as mailing" box (most filers).
    # When checked, principal address fields must be left blank per form instructions.
    result[fields["same_as_mailing_cb"]] = "/1"
    result[fields["principal_street"]] = ""
    result[fields["principal_apt"]] = ""
    result[fields["principal_city"]] = ""
    result[fields["principal_state"]] = ""
    result[fields["principal_zip"]] = ""

    # --- Page 1: Filing status ---
    fs_value = _FILING_STATUS_RADIO.get(tp.filing_status)
    if fs_value:
        result[fields["filing_status"]] = fs_value

    # MFS: enter spouse name
    if tp.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY and tp.spouse_name:
        result[fields["mfs_spouse_name"]] = tp.spouse_name

    # --- Page 1: Exemptions (lines 7-9) ---

    # Line 7: Personal exemptions
    is_joint = tp.filing_status == FilingStatus.MARRIED_FILING_JOINTLY
    personal_count = 2 if is_joint else 1
    result[fields["line7_personal_num"]] = str(personal_count)
    result[fields["line7_personal_amt"]] = str(personal_count * 153)

    # Line 10: Dependents & Line 11: Total exemption amount
    # (handled on page 2 below)

    # --- Page 2: Header ---
    header_name = tp.name
    if tp.spouse_name and is_joint:
        header_name = f"{tp.name} & {tp.spouse_name}"
    result[fields["p2_name"]] = header_name
    if tp.ssn:
        result[fields["p2_ssn"]] = tp.ssn.replace("-", "")

    # --- Page 2: Dependents (line 10) ---
    deps = tp.dependents or []
    dep_fields = [
        ("dep1_first", "dep1_last", "dep1_ssn", "dep1_relationship"),
        ("dep2_first", "dep2_last", "dep2_ssn", "dep2_relationship"),
        ("dep3_first", "dep3_last", "dep3_ssn", "dep3_relationship"),
    ]
    for i, dep in enumerate(deps[:3]):
        first_key, last_key, ssn_key, rel_key = dep_fields[i]
        dep_name_parts = dep.name.split()
        if len(dep_name_parts) > 1:
            result[fields[first_key]] = " ".join(dep_name_parts[:-1])
            result[fields[last_key]] = dep_name_parts[-1]
        else:
            result[fields[first_key]] = dep.name
        if dep.ssn:
            result[fields[ssn_key]] = dep.ssn.strip().replace("-", "")
        result[fields[rel_key]] = dep.relationship

    num_deps = len(deps)
    if num_deps > 0:
        result[fields["line10_dep_num"]] = str(num_deps)
        result[fields["line10_dep_amt"]] = str(num_deps * 475)

    # Line 11: Total exemption amount
    total_exemption = personal_count * 153 + num_deps * 475
    result[fields["line11_exemption_amount"]] = str(total_exemption)

    # --- Page 2: Taxable Income (lines 12-19) ---

    # Line 12: State wages (sum of W-2 Box 16 state wages)
    state_wages = sum(w.state_wages for w in tax_return.w2_forms)
    if state_wages > 0:
        result[fields["line12_state_wages"]] = _dollars(state_wages)

    # Line 13: Federal AGI
    if fed:
        result[fields["line13_federal_agi"]] = _dollars(fed.adjusted_gross_income)

    # CA adjustments (lines 14, 16)
    if fed and ca.adjusted_gross_income != fed.adjusted_gross_income:
        ca_adj = ca.adjusted_gross_income - fed.adjusted_gross_income
        if ca_adj < 0:
            result[fields["line14_ca_subtractions"]] = _dollars(abs(ca_adj))
            # Line 15 = Line 13 - Line 14
            result[fields["line15_subtotal"]] = _dollars(
                fed.adjusted_gross_income - abs(ca_adj)
            )
        else:
            result[fields["line16_ca_additions"]] = _dollars(ca_adj)
            # Line 15 = Line 13 (no subtraction)
            result[fields["line15_subtotal"]] = _dollars(
                fed.adjusted_gross_income
            )
    elif fed:
        result[fields["line15_subtotal"]] = _dollars(fed.adjusted_gross_income)

    # Line 17: CA AGI
    result[fields["line17_ca_agi"]] = _dollars(ca.adjusted_gross_income)

    # Line 18: Deductions (itemized or standard)
    result[fields["line18_deductions"]] = _dollars(ca.deductions)

    # Line 19: Taxable income
    result[fields["line19_taxable_income"]] = _dollars(ca.taxable_income)

    # --- Page 2: Tax section (lines 31-35) ---

    # Line 31: Base tax from tax table (excluding mental health surcharge)
    base_tax = ca.tax_before_credits - ca.ca_mental_health_tax
    result[fields["line31_tax"]] = _dollars(base_tax)

    # Line 32: Exemption credits
    if ca.ca_exemption_credit > 0:
        result[fields["line32_exemption_credits"]] = _dollars(
            ca.ca_exemption_credit
        )

    # Line 33: Line 31 - Line 32
    line33 = max(0, base_tax - ca.ca_exemption_credit)
    result[fields["line33_subtotal"]] = _dollars(line33)

    # Line 35: same as line 33 if no line 34
    result[fields["line35_total"]] = _dollars(line33)

    # --- Page 3: Credits (lines 46-48) ---

    # Line 46: Renter's credit
    if ca.ca_renters_credit > 0:
        result[fields["line46_renters_credit"]] = _dollars(
            ca.ca_renters_credit
        )

    # Line 47: Total credits (renters + any other)
    total_credits = ca.ca_renters_credit
    if total_credits > 0:
        result[fields["line47_total_credits"]] = _dollars(total_credits)

    # Line 48: Line 35 - Line 47
    line48 = max(0, line33 - total_credits)
    result[fields["line48_net_tax"]] = _dollars(line48)

    # --- Page 3: Other Taxes (lines 61-64) ---

    # Line 62: Mental Health / Behavioral Health Tax (1% on income > $1M)
    if ca.ca_mental_health_tax > 0:
        result[fields["line62_mental_health_tax"]] = _dollars(
            ca.ca_mental_health_tax
        )

    # Line 64: Total tax = Line 48 + Line 61 + Line 62 + Line 63
    total_tax = line48 + ca.ca_mental_health_tax
    result[fields["line64_total_tax"]] = _dollars(total_tax)

    # --- Page 3: Payments (lines 71-78) ---

    # Line 71: CA income tax withheld
    result[fields["line71_ca_withheld"]] = _dollars(ca.tax_withheld)

    # Line 72: Estimated payments
    if ca.estimated_payments > 0:
        result[fields["line72_estimated_payments"]] = _dollars(
            ca.estimated_payments
        )

    # Line 78: Total payments
    total_payments = ca.total_payments
    if ca.ca_sdi > 0:
        total_payments += ca.ca_sdi
    result[fields["line78_total_payments"]] = _dollars(total_payments)

    # --- Page 3: Overpaid / Tax Due (lines 93-97) ---

    # Line 93: Payments balance (line 78 - line 91 use tax)
    result[fields["line93_payments_balance"]] = _dollars(total_payments)

    # Line 95: After ISR penalty (= line 93 if no ISR)
    result[fields["line95_after_isr"]] = _dollars(total_payments)

    # Refund or owed
    refund_or_owed = ca.refund_or_owed
    if ca.ca_sdi > 0:
        refund_or_owed += ca.ca_sdi

    if refund_or_owed > 0:
        # Line 97: Overpaid
        result[fields["line97_overpaid"]] = _dollars(refund_or_owed)
        # Line 99: Refund
        result[fields["line99_refund"]] = _dollars(refund_or_owed)
    elif refund_or_owed < 0:
        # Line 100: Amount owed
        result[fields["line100_amount_owed"]] = _dollars(abs(refund_or_owed))

    return result
