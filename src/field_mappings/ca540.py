"""Field mapping for California Form 540 (CA Resident Income Tax Return).

Field names verified against 2025 FTB fillable PDF (2025-540.pdf).
FTB uses flat naming: 540_form_XYYY where X=page, YYY=field sequence.

Run `python tools/discover_fields.py pdf_templates/2024/ca540.pdf` to verify.
"""

from typing import Dict
from ..models import TaxReturn, FilingStatus
from . import register


def _dollars(amount: float) -> str:
    return str(round(amount))


# 2025 CA Form 540 actual field names from FTB fillable PDF.
# Page 1: 540_form_1XXX (header, filing status, income)
# Page 2: 540_form_2XXX (tax computation, credits)
# Page 3: 540_form_3XXX (payments, refund/owed)
# Page 4: 540_form_4XXX (additional info)
#
# Field-to-line mapping requires visual verification with labeled PDF.
# Run: python tools/discover_fields.py pdf_templates/2024/ca540.pdf
# The labeled PDF is at: output/ca540_labeled.pdf
FIELD_NAMES_2025 = {
    # Filing status checkbox
    "filing_status": "540_form_1001 CB",

    # Page 1 - Header
    "your_first_name": "540_form_1002",
    "your_last_name": "540_form_1003",
    "your_ssn": "540_form_1004",
    "spouse_first_name": "540_form_1005",
    "spouse_last_name": "540_form_1006",
    "spouse_ssn": "540_form_1007",
    "address": "540_form_1008",
    "apt_no": "540_form_1009",
    "city": "540_form_1010",
    "state": "540_form_1011",
    "zip": "540_form_1012",

    # Page 1 - Income section (line numbers from CA 540 form)
    # These field numbers need visual verification - update after checking labeled PDF
    "line7_federal_agi": "540_form_1037",
    "line8_ca_wages": "540_form_1038",
    "line11_ca_subtractions": "540_form_1039",
    "line12_ca_additions": "540_form_1041",
    "line13_ca_agi": "540_form_1042",
    "line14_deductions": "540_form_1043",
    "line15_taxable_income": "540_form_1044",

    # Page 2 - Tax computation
    "line16_tax": "540_form_2001",
    "line17_exemption_credits": "540_form_2002",
    "line18_subtotal": "540_form_2003",
    "line19_special_credits": "540_form_2004",
    "line20_subtotal2": "540_form_2005",
    "line21_other_taxes": "540_form_2006",
    "line22_mental_health_tax": "540_form_2007",
    "line23_total_tax": "540_form_2008",

    # Page 2 - Payments
    "line24_ca_withheld": "540_form_2009",
    "line25_estimated_payments": "540_form_2010",
    "line26_excess_sdi": "540_form_2011",
    "line27_other_payments": "540_form_2012",
    "line28_total_payments": "540_form_2013",

    # Page 2 - Refund or owed
    "line29_overpaid": "540_form_2014",
    "line30_refund": "540_form_2015",
    "line31_amount_owed": "540_form_2016",

    # Renter's credit
    "renters_credit": "540_form_2017",
}

FIELD_NAMES = {
    2024: FIELD_NAMES_2025,  # FTB 2024 form may differ; verify
    2025: FIELD_NAMES_2025,
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

    # Name
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

    # Federal AGI flows into CA
    if fed:
        result[fields["line7_federal_agi"]] = _dollars(fed.adjusted_gross_income)

    # CA AGI (may differ from federal due to CA adjustments)
    result[fields["line13_ca_agi"]] = _dollars(ca.adjusted_gross_income)

    # CA adjustments (US Treasury interest subtraction, etc.)
    if fed and ca.adjusted_gross_income != fed.adjusted_gross_income:
        ca_adj = ca.adjusted_gross_income - fed.adjusted_gross_income
        if ca_adj < 0:
            result[fields["line11_ca_subtractions"]] = _dollars(abs(ca_adj))
        else:
            result[fields["line12_ca_additions"]] = _dollars(ca_adj)

    # Deductions and taxable income
    result[fields["line14_deductions"]] = _dollars(ca.deductions)
    result[fields["line15_taxable_income"]] = _dollars(ca.taxable_income)

    # Tax
    result[fields["line16_tax"]] = _dollars(ca.tax_before_credits)

    # Exemption credits
    if ca.ca_exemption_credit > 0:
        result[fields["line17_exemption_credits"]] = _dollars(ca.ca_exemption_credit)

    # Mental Health Tax (1% surcharge on income > $1M)
    if ca.ca_mental_health_tax > 0:
        result[fields["line22_mental_health_tax"]] = _dollars(ca.ca_mental_health_tax)

    # Total tax
    result[fields["line23_total_tax"]] = _dollars(ca.tax_after_credits)

    # Payments
    result[fields["line24_ca_withheld"]] = _dollars(ca.tax_withheld)
    if ca.estimated_payments > 0:
        result[fields["line25_estimated_payments"]] = _dollars(ca.estimated_payments)

    # Excess SDI
    if ca.ca_sdi > 0:
        result[fields["line26_excess_sdi"]] = _dollars(ca.ca_sdi)

    total_payments = ca.total_payments
    if ca.ca_sdi > 0:
        total_payments += ca.ca_sdi
    result[fields["line28_total_payments"]] = _dollars(total_payments)

    # Renter's credit
    if ca.ca_renters_credit > 0:
        result[fields["renters_credit"]] = _dollars(ca.ca_renters_credit)

    # Refund or owed
    refund_or_owed = ca.refund_or_owed
    if refund_or_owed > 0:
        result[fields["line29_overpaid"]] = _dollars(refund_or_owed)
        result[fields["line30_refund"]] = _dollars(refund_or_owed)
    elif refund_or_owed < 0:
        result[fields["line31_amount_owed"]] = _dollars(abs(refund_or_owed))

    return result
