"""Tax Summary Report Generator.

Generates detailed reports mimicking the structure of:
- Federal Form 1040
- California Form 540
- Schedule E (Rental Income)
- Schedule A (Itemized Deductions)
"""

from .models import TaxReturn, TaxCalculation, ScheduleESummary, ScheduleAResult


def fmt(amount: float) -> str:
    """Format amount as currency."""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def _sep(char: str = "=", length: int = 72) -> str:
    return char * length


def _line(label: str, amount, width: int = 55) -> str:
    """Format a single line item."""
    return f"  {label:<{width}} {fmt(amount) if isinstance(amount, (int, float)) else amount:>15}"


def generate_schedule_e_report(summary: ScheduleESummary) -> str:
    """Generate Schedule E (Supplemental Income) report."""
    lines = []
    lines.append("")
    lines.append(_sep("-", 72))
    lines.append("  SCHEDULE E - Supplemental Income and Loss (Rental Real Estate)")
    lines.append(_sep("-", 72))

    for i, prop in enumerate(summary.properties, 1):
        lines.append(f"\n  Property {i}: {prop.address}")
        lines.append("  " + "-" * 68)
        lines.append(_line("  Gross Rents Received", prop.gross_income))
        lines.append(_line("  Total Expenses", prop.total_expenses))
        lines.append(_line("  Depreciation (27.5-yr straight-line)", prop.depreciation))
        lines.append("  " + "-" * 68)
        lines.append(_line("  Net Rental Income (Loss)", prop.net_income))

    lines.append("\n  " + "-" * 68)
    lines.append(_line("TOTAL Net Rental Income (Loss)", summary.total_net_rental_income))
    return "\n".join(lines)


def generate_schedule_a_report(result: ScheduleAResult, jurisdiction: str = "Federal") -> str:
    """Generate Schedule A (Itemized Deductions) report."""
    lines = []
    lines.append("")
    lines.append(_sep("-", 72))
    title = "SCHEDULE A - Itemized Deductions"
    if jurisdiction != "Federal":
        title += f" ({jurisdiction})"
    lines.append(f"  {title}")
    lines.append(_sep("-", 72))

    lines.append(_line("Medical and Dental (after 7.5% AGI floor)", result.medical_deduction))

    if jurisdiction == "Federal":
        lines.append(_line("State/Local Taxes (SALT, capped at $10,000)", result.salt_deduction))
        if result.salt_uncapped > result.salt_deduction:
            lines.append(_line("  (Uncapped SALT would be)", result.salt_uncapped))
    else:
        lines.append(_line("Taxes Paid (no SALT cap in CA)", result.salt_deduction))

    lines.append(_line("Mortgage Interest", result.mortgage_interest_deduction))
    lines.append(_line("Charitable Contributions", result.charitable_deduction))
    if result.other_deductions > 0:
        lines.append(_line("Other Deductions", result.other_deductions))
    if result.ca_itemized_limitation > 0:
        lines.append(_line("CA Itemized Deduction Limitation", -result.ca_itemized_limitation))
    lines.append("  " + "-" * 68)
    lines.append(_line("Total Itemized Deductions", result.total_itemized))
    lines.append(_line("Standard Deduction", result.standard_deduction))
    lines.append("  " + "-" * 68)

    if result.use_itemized:
        lines.append(_line(">>> USING ITEMIZED DEDUCTIONS", result.deduction_amount))
    else:
        lines.append(_line(">>> USING STANDARD DEDUCTION", result.deduction_amount))

    return "\n".join(lines)


def generate_federal_report(calc: TaxCalculation) -> str:
    """Generate a report mimicking Form 1040."""
    lines = []
    lines.append("")
    lines.append(_sep("=", 72))
    lines.append(f"  FORM 1040 - U.S. Individual Income Tax Return (Tax Year {calc.tax_year})")
    lines.append(_sep("=", 72))

    # Income section
    lines.append("\n  INCOME")
    lines.append("  " + "-" * 68)
    lines.append(_line("1-8. Total Income (all sources)", calc.gross_income))
    lines.append(_line("10.  Adjustments to Income", calc.adjustments))
    lines.append(_line("11.  Adjusted Gross Income (AGI)", calc.adjusted_gross_income))

    # Schedule E
    if calc.schedule_e_summary and calc.schedule_e_summary.properties:
        lines.append(generate_schedule_e_report(calc.schedule_e_summary))

    # Schedule A
    if calc.schedule_a_result:
        lines.append(generate_schedule_a_report(calc.schedule_a_result, "Federal"))
    else:
        lines.append("")
        lines.append(f"  DEDUCTIONS ({calc.deduction_method.upper()})")
        lines.append("  " + "-" * 68)
        lines.append(_line("12.  Deduction Amount", calc.deductions))

    # Tax computation
    lines.append("")
    lines.append("  TAX COMPUTATION")
    lines.append("  " + "-" * 68)
    lines.append(_line("15.  Taxable Income", calc.taxable_income))

    if calc.bracket_breakdown:
        lines.append("")
        lines.append("  Tax Bracket Breakdown:")
        for b in calc.bracket_breakdown:
            rate_pct = f"{b['rate']*100:.1f}%"
            lines.append(f"    {b['bracket']:>30}  @{rate_pct:>6}  = {fmt(b['tax']):>12}")

    income_tax = calc.tax_before_credits - calc.self_employment_tax - calc.additional_medicare_tax
    lines.append("\n  " + "-" * 68)
    lines.append(_line("16.  Income Tax", income_tax))

    if calc.self_employment_tax > 0:
        lines.append(_line("23.  Self-Employment Tax", calc.self_employment_tax))

    if calc.additional_medicare_tax > 0:
        lines.append(_line("      Additional Medicare Tax (0.9%)", calc.additional_medicare_tax))

    lines.append(_line("24.  Tax Before Credits", calc.tax_before_credits))

    # Credits
    lines.append("")
    lines.append("  CREDITS")
    lines.append("  " + "-" * 68)
    if calc.num_qualifying_children > 0:
        lines.append(_line(
            f"     Child Tax Credit ({calc.num_qualifying_children} children x $2,000)",
            calc.child_tax_credit
        ))
    if calc.credits > calc.child_tax_credit:
        lines.append(_line("     Other Credits", calc.credits - calc.child_tax_credit))
    lines.append(_line("     Total Credits", calc.credits))

    lines.append("\n  " + "-" * 68)
    lines.append(_line("TAX AFTER CREDITS", calc.tax_after_credits))

    # Payments
    lines.append("")
    lines.append("  PAYMENTS")
    lines.append("  " + "-" * 68)
    lines.append(_line("     Federal Tax Withheld", calc.tax_withheld))
    if calc.estimated_payments > 0:
        lines.append(_line("     Estimated Tax Payments", calc.estimated_payments))
    lines.append(_line("     Total Payments", calc.total_payments))

    # Refund or Amount Owed
    lines.append("\n  " + "=" * 68)
    refund = calc.refund_or_owed
    if refund >= 0:
        lines.append(_line("FEDERAL REFUND", refund))
    else:
        lines.append(_line("FEDERAL TAX OWED", abs(refund)))

    return "\n".join(lines)


def generate_california_report(calc: TaxCalculation) -> str:
    """Generate a report mimicking California Form 540."""
    lines = []
    lines.append("")
    lines.append(_sep("=", 72))
    lines.append(f"  FORM 540 - California Resident Income Tax Return ({calc.tax_year})")
    lines.append(_sep("=", 72))

    # Income
    lines.append("\n  INCOME")
    lines.append("  " + "-" * 68)
    lines.append(_line("CA Gross Income", calc.gross_income))
    lines.append(_line("CA Adjustments", calc.adjustments))
    lines.append(_line("CA Adjusted Gross Income", calc.adjusted_gross_income))

    # Deductions
    if calc.schedule_a_result:
        lines.append(generate_schedule_a_report(calc.schedule_a_result, "California"))
    else:
        lines.append("")
        lines.append(f"  DEDUCTIONS ({calc.deduction_method.upper()})")
        lines.append("  " + "-" * 68)
        lines.append(_line("CA Deduction Amount", calc.deductions))

    # Tax
    lines.append("")
    lines.append("  TAX COMPUTATION")
    lines.append("  " + "-" * 68)
    lines.append(_line("CA Taxable Income", calc.taxable_income))

    if calc.bracket_breakdown:
        lines.append("")
        lines.append("  CA Tax Bracket Breakdown:")
        for b in calc.bracket_breakdown:
            rate_pct = f"{b['rate']*100:.1f}%"
            lines.append(f"    {b['bracket']:>30}  @{rate_pct:>6}  = {fmt(b['tax']):>12}")

    base_tax = calc.tax_before_credits - calc.ca_mental_health_tax
    lines.append("\n  " + "-" * 68)
    lines.append(_line("CA Base Tax", base_tax))

    if calc.ca_mental_health_tax > 0:
        lines.append(_line("Mental Health Services Tax (1% > $1M)", calc.ca_mental_health_tax))

    lines.append(_line("Tax Before Credits", calc.tax_before_credits))

    # Credits
    lines.append("")
    lines.append("  CREDITS")
    lines.append("  " + "-" * 68)
    if calc.ca_exemption_credit > 0:
        lines.append(_line("Exemption Credit", calc.ca_exemption_credit))
    if calc.ca_renters_credit > 0:
        lines.append(_line("Renter's Credit", calc.ca_renters_credit))
    other_ca_credits = calc.credits - calc.ca_exemption_credit - calc.ca_renters_credit
    if other_ca_credits > 0:
        lines.append(_line("Other Credits", other_ca_credits))
    lines.append(_line("Total Credits", calc.credits))

    lines.append("\n  " + "-" * 68)
    lines.append(_line("CA TAX AFTER CREDITS", calc.tax_after_credits))

    # Payments
    lines.append("")
    lines.append("  PAYMENTS")
    lines.append("  " + "-" * 68)
    lines.append(_line("State Tax Withheld", calc.tax_withheld))
    if calc.estimated_payments > 0:
        lines.append(_line("Estimated Tax Payments", calc.estimated_payments))
    lines.append(_line("Total Payments", calc.total_payments))

    # Refund / Owed
    lines.append("\n  " + "=" * 68)
    refund = calc.refund_or_owed
    if refund >= 0:
        lines.append(_line("CA STATE REFUND", refund))
    else:
        lines.append(_line("CA STATE TAX OWED", abs(refund)))

    return "\n".join(lines)


def generate_full_report(tax_return: TaxReturn) -> str:
    """
    Generate the complete Tax Summary Report.

    Includes:
    - Taxpayer information
    - Income summary
    - Federal Form 1040 report
    - California Form 540 report
    - Combined totals
    """
    lines = []

    # Header
    lines.append("")
    lines.append(_sep("*", 72))
    lines.append(f"  TAX SUMMARY REPORT - Tax Year {tax_return.tax_year}")
    lines.append(_sep("*", 72))

    # Taxpayer info
    tp = tax_return.taxpayer
    lines.append(f"\n  Taxpayer:       {tp.name}")
    lines.append(f"  Filing Status:  {tp.filing_status.value.replace('_', ' ').title()}")
    lines.append(f"  Age:            {tp.age}")
    if tp.dependents:
        lines.append(f"  Dependents:     {tp.num_dependents}")
        for dep in tp.dependents:
            ctc = " (CTC eligible)" if dep.qualifies_for_child_tax_credit else ""
            lines.append(f"    - {dep.name}, age {dep.age} ({dep.relationship}){ctc}")

    # Income summary
    inc = tax_return.income
    lines.append("")
    lines.append(_sep("-", 72))
    lines.append("  INCOME SUMMARY")
    lines.append(_sep("-", 72))
    lines.append(_line("Wages (W-2)", inc.wages))
    lines.append(_line("Interest Income (1099-INT)", inc.interest_income))
    lines.append(_line("Dividend Income (1099-DIV)", inc.dividend_income))
    if inc.qualified_dividends > 0:
        lines.append(_line("  Qualified Dividends", inc.qualified_dividends))
    lines.append(_line("Capital Gains (1099-B/DIV)", inc.capital_gains))
    lines.append(_line("Self-Employment (1099-NEC)", inc.self_employment_income))
    lines.append(_line("Retirement (1099-R)", inc.retirement_income))
    lines.append(_line("Net Rental Income (Schedule E)", inc.rental_income))
    lines.append(_line("Other Income", inc.other_income))
    lines.append("  " + "-" * 68)
    lines.append(_line("TOTAL GROSS INCOME", inc.total_income))

    # Estimated payments summary
    if tax_return.estimated_payments:
        lines.append("")
        lines.append(_sep("-", 72))
        lines.append("  ESTIMATED TAX PAYMENTS")
        lines.append(_sep("-", 72))
        for ep in tax_return.estimated_payments:
            date_str = ep.payment_date.strftime("%m/%d/%Y") if ep.payment_date else "N/A"
            lines.append(f"  {ep.period:>4} ({ep.jurisdiction:>10}) - {date_str}: {fmt(ep.amount):>12}")
        lines.append("  " + "-" * 68)
        lines.append(_line("Federal Estimated Payments", tax_return.total_federal_estimated_payments))
        lines.append(_line("CA Estimated Payments", tax_return.total_state_estimated_payments))

    # Federal report
    if tax_return.federal_calculation:
        lines.append(generate_federal_report(tax_return.federal_calculation))

    # California report
    if tax_return.state_calculation:
        lines.append(generate_california_report(tax_return.state_calculation))

    # Combined summary
    lines.append("")
    lines.append(_sep("*", 72))
    lines.append("  COMBINED TAX SUMMARY")
    lines.append(_sep("*", 72))

    fed = tax_return.federal_calculation
    state = tax_return.state_calculation

    fed_refund = fed.refund_or_owed if fed else 0
    state_refund = state.refund_or_owed if state else 0

    if fed:
        fed_rate = fed.tax_after_credits / fed.gross_income * 100 if fed.gross_income > 0 else 0
        lines.append(_line("Federal Tax After Credits", fed.tax_after_credits))
        lines.append(_line("Federal Effective Rate", f"{fed_rate:.2f}%"))
    if state:
        state_rate = state.tax_after_credits / state.gross_income * 100 if state.gross_income > 0 else 0
        lines.append(_line("CA Tax After Credits", state.tax_after_credits))
        lines.append(_line("CA Effective Rate", f"{state_rate:.2f}%"))

    total_tax = (fed.tax_after_credits if fed else 0) + (state.tax_after_credits if state else 0)
    total_income = fed.gross_income if fed else (state.gross_income if state else 0)
    combined_rate = total_tax / total_income * 100 if total_income > 0 else 0

    lines.append("  " + "-" * 68)
    lines.append(_line("Combined Tax Liability", total_tax))
    lines.append(_line("Combined Effective Rate", f"{combined_rate:.2f}%"))

    lines.append("\n  " + "=" * 68)
    total = fed_refund + state_refund
    if total >= 0:
        lines.append(_line("TOTAL REFUND", total))
    else:
        lines.append(_line("TOTAL TAX OWED", abs(total)))

    lines.append("")
    lines.append(_sep("*", 72))
    lines.append("  NOTE: This calculation is for reference only and may not reflect")
    lines.append("  actual tax liability. Please consult a tax professional.")
    lines.append(_sep("*", 72))

    return "\n".join(lines)
