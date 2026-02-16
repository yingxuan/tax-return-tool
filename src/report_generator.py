"""Tax Summary Report Generator.

Generates detailed reports mimicking the structure of:
- Federal Form 1040
- California Form 540
- Schedule E (Rental Income)
- Schedule A (Itemized Deductions)
"""

from .models import TaxReturn, TaxCalculation, ScheduleESummary, ScheduleAResult
from .config_loader import STATES_NO_INCOME_TAX


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

    # Passive Activity Loss Limitations (Form 8582)
    if summary.pal_disallowed > 0:
        lines.append("")
        lines.append("  Form 8582 - Passive Activity Loss Limitations:")
        lines.append(_line("  Total Rental Loss (before PAL)", summary.total_net_rental_income))
        lines.append(_line("  Disallowed Passive Loss", summary.pal_disallowed))
        allowed = abs(summary.total_net_rental_income) - summary.pal_disallowed
        if allowed > 0:
            lines.append(_line("  Allowed Loss (flows to AGI)", -allowed))
        else:
            lines.append(_line("  Allowed Loss (flows to AGI)", 0.0))
        lines.append(_line("  PAL Carryover to Next Year", summary.pal_carryover))

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
            lines.append("    (includes: state income tax withholding + property tax + VLF)")
    else:
        # CA does NOT allow deducting CA state income tax on the CA return.
        # CA SALT = real estate taxes + personal property taxes + VLF only.
        lines.append(_line("Property & Personal Prop. Taxes (no SALT cap)", result.salt_deduction))
        lines.append("    (CA excludes state income tax; only real estate tax + VLF)")

    lines.append(_line("Mortgage Interest", result.mortgage_interest_deduction))
    lines.append(_line("Charitable Contributions", result.charitable_deduction))
    if result.other_deductions > 0:
        lines.append(_line("Other Deductions", result.other_deductions))
    if result.ca_misc_deduction > 0:
        lines.append(_line("Misc. Deductions (CA-only, after 2% AGI floor)", result.ca_misc_deduction))
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
    lines.append("    (If this differs from prior year, verify SALT, mortgage interest, and charitable contributions.)")

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

    income_tax = calc.tax_before_credits - calc.self_employment_tax - calc.additional_medicare_tax - calc.niit
    lines.append("\n  " + "-" * 68)

    if calc.qualified_dividend_ltcg_tax > 0:
        lines.append(_line("16.  Ordinary Income Tax", calc.ordinary_income_tax))
        lines.append(_line("      QD/LTCG Tax (preferential rates)", calc.qualified_dividend_ltcg_tax))
    else:
        lines.append(_line("16.  Income Tax", income_tax))

    if calc.self_employment_tax > 0:
        lines.append(_line("23.  Self-Employment Tax", calc.self_employment_tax))

    if calc.additional_medicare_tax > 0:
        lines.append(_line("      Additional Medicare Tax (0.9%)", calc.additional_medicare_tax))

    if calc.niit > 0:
        lines.append(_line("      Net Investment Income Tax (3.8%)", calc.niit))

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


def generate_generic_state_report(calc: TaxCalculation) -> str:
    """Generate a state tax report for non-CA states (e.g. New York IT-201)."""
    lines = []
    lines.append("")
    lines.append(_sep("=", 72))
    lines.append(f"  {calc.jurisdiction.upper()} STATE INCOME TAX ({calc.tax_year})")
    lines.append(_sep("=", 72))

    lines.append("\n  INCOME")
    lines.append("  " + "-" * 68)
    lines.append(_line("Gross Income", calc.gross_income))
    lines.append(_line("Adjustments", calc.adjustments))
    lines.append(_line("Adjusted Gross Income", calc.adjusted_gross_income))

    lines.append("\n  DEDUCTIONS")
    lines.append("  " + "-" * 68)
    lines.append(_line(f"Deduction ({calc.deduction_method})", calc.deductions))

    lines.append("\n  TAX COMPUTATION")
    lines.append("  " + "-" * 68)
    lines.append(_line("Taxable Income", calc.taxable_income))
    if calc.bracket_breakdown:
        lines.append("")
        lines.append(f"  {calc.jurisdiction} Tax Bracket Breakdown:")
        for b in calc.bracket_breakdown:
            rate_pct = f"{b['rate']*100:.1f}%"
            lines.append(f"    {b['bracket']:>30}  @{rate_pct:>6}  = {fmt(b['tax']):>12}")
    lines.append("  " + "-" * 68)
    lines.append(_line("Tax Before Credits", calc.tax_before_credits))
    lines.append(_line("Credits", calc.credits))
    lines.append(_line("TAX AFTER CREDITS", calc.tax_after_credits))

    lines.append("\n  PAYMENTS")
    lines.append("  " + "-" * 68)
    lines.append(_line("State Tax Withheld", calc.tax_withheld))
    if calc.estimated_payments > 0:
        lines.append(_line("Estimated Payments", calc.estimated_payments))
    lines.append(_line("Total Payments", calc.total_payments))

    refund = calc.refund_or_owed
    lines.append("\n  " + "=" * 68)
    if refund >= 0:
        lines.append(_line(f"{calc.jurisdiction.upper()} STATE REFUND", refund))
    else:
        lines.append(_line(f"{calc.jurisdiction.upper()} STATE TAX OWED", abs(refund)))

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
    if inc.dividend_income == 0:
        lines.append("    (If you have 1099-DIV forms, verify they were parsed and amounts extracted.)")
    if inc.qualified_dividends > 0:
        lines.append(_line("  Qualified Dividends", inc.qualified_dividends))
        lines.append("    (Verify against 1099-DIV Box 1b; set qualified_dividends in config if extraction is low.)")
    lines.append(_line("Capital Gains (1099-B/DIV)", inc.capital_gains))
    if inc.capital_gains <= 0:
        lines.append("    (If you have broker/1099-B statements with gains, set Document folder to a path that includes them, e.g. .../2025/1099/brokers.)")
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

    # State report: CA (Form 540), other states (generic), or message if not calculated
    state_code = getattr(tax_return, "state_of_residence", None) or "CA"
    if tax_return.state_calculation:
        if tax_return.state_calculation.jurisdiction == "California":
            lines.append(generate_california_report(tax_return.state_calculation))
        else:
            lines.append(generate_generic_state_report(tax_return.state_calculation))
    elif state_code and state_code != "CA":
        lines.append("")
        lines.append(_sep("-", 72))
        lines.append(f"  STATE OF RESIDENCE: {state_code}")
        lines.append(_sep("-", 72))
        if state_code in STATES_NO_INCOME_TAX:
            lines.append("  No state income tax in this state.")
        else:
            lines.append(f"  State income tax for {state_code} is not calculated by this tool.")
            lines.append("  Use federal summary and W-2 state withholding for reference.")
        lines.append("")

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
        lines.append(_line(f"{state.jurisdiction} Tax After Credits", state.tax_after_credits))
        lines.append(_line(f"{state.jurisdiction} Effective Rate", f"{state_rate:.2f}%"))

    total_tax = (fed.tax_after_credits if fed else 0) + (state.tax_after_credits if state else 0)
    total_income = fed.gross_income if fed else (state.gross_income if state else 0)
    combined_rate = total_tax / total_income * 100 if total_income > 0 else 0

    lines.append("  " + "-" * 68)
    lines.append(_line("Combined Tax Liability", total_tax))
    lines.append(_line("Combined Effective Rate", f"{combined_rate:.2f}%"))

    # Detailed payment breakdown
    lines.append("")
    lines.append("  " + "-" * 68)
    lines.append("  PAYMENTS DETAIL")
    lines.append("  " + "-" * 68)
    if fed:
        lines.append(_line("  Federal Withheld (W-2/1099)", fed.tax_withheld))
        if fed.estimated_payments > 0:
            lines.append(_line("  Federal Estimated Payments", fed.estimated_payments))
        lines.append(_line("  Federal Total Payments", fed.total_payments))
    if state:
        lines.append(_line(f"  {state.jurisdiction} Withheld (W-2/1099)", state.tax_withheld))
        if state.estimated_payments > 0:
            lines.append(_line(f"  {state.jurisdiction} Estimated Payments", state.estimated_payments))
        lines.append(_line(f"  {state.jurisdiction} Total Payments", state.total_payments))

    total_payments = (fed.total_payments if fed else 0) + (state.total_payments if state else 0)
    lines.append("  " + "-" * 68)
    lines.append(_line("  Total All Payments", total_payments))

    # Capital loss carryover info (if available)
    tr = tax_return
    if hasattr(tr, '_capital_loss_carryover_applied') and tr._capital_loss_carryover_applied > 0:
        lines.append("")
        lines.append("  " + "-" * 68)
        lines.append("  CAPITAL LOSS CARRYOVER (Schedule D)")
        lines.append("  " + "-" * 68)
        lines.append(_line("  Prior Year Carryover (starting)", tr._capital_loss_carryover_applied))
        used = getattr(tr, '_capital_loss_deductible_used', None)
        if used is not None and used > 0:
            lines.append(_line("  Amount Used This Year (max $3,000)", used))
        lines.append(_line("  Remaining Carryover to Next Year", tr._capital_loss_carryover_remaining))

    # Refund / Owed per jurisdiction
    lines.append("")
    lines.append("  " + "-" * 68)
    lines.append("  REFUND / AMOUNT OWED")
    lines.append("  " + "-" * 68)
    if fed:
        if fed_refund >= 0:
            lines.append(_line("  Federal Refund", fed_refund))
        else:
            lines.append(_line("  Federal Tax Owed", abs(fed_refund)))
    if state:
        if state_refund >= 0:
            lines.append(_line(f"  {state.jurisdiction} Refund", state_refund))
        else:
            lines.append(_line(f"  {state.jurisdiction} Tax Owed", abs(state_refund)))

    lines.append("\n  " + "=" * 68)
    total = fed_refund + state_refund
    if total >= 0:
        lines.append(_line("NET TOTAL REFUND", total))
    else:
        lines.append(_line("NET TOTAL TAX OWED", abs(total)))

    lines.append("")
    lines.append(_sep("*", 72))
    lines.append("  NOTE: This calculation is for reference only and may not reflect")
    lines.append("  actual tax liability. Please consult a tax professional.")
    lines.append(_sep("*", 72))

    return "\n".join(lines)


def _row_html(label: str, amount, css_class: str = "") -> str:
    """One row for HTML report: label left, amount right."""
    if isinstance(amount, (int, float)):
        amt_str = fmt(amount)
    else:
        amt_str = str(amount)
    cls = f' class="{css_class}"' if css_class else ""
    return f'<div class="report-row"{cls}><span class="report-label">{_escape_html(label)}</span><span class="report-amount">{_escape_html(amt_str)}</span></div>'


def _escape_html(s: str) -> str:
    if s is None:
        return ""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _section_html(title: str, rows: list, level: int = 2) -> str:
    """Section with heading and rows."""
    tag = "h2" if level == 2 else "h3"
    parts = [f'<section class="report-section">', f'<{tag} class="report-section-title">{_escape_html(title)}</{tag}>']
    parts.extend(rows)
    parts.append("</section>")
    return "\n".join(parts)


def generate_full_report_html(tax_return: TaxReturn) -> str:
    """Generate the tax summary as user-friendly HTML (sections, rows, spacing)."""
    parts = ['<div class="tax-report">']
    tp = tax_return.taxpayer
    inc = tax_return.income

    # Header
    parts.append(f'<section class="report-section report-header">')
    parts.append(f'<h1 class="report-main-title">Tax Summary — {tax_return.tax_year}</h1>')
    parts.append(f'<div class="report-meta">')
    parts.append(f'<span><strong>{_escape_html(tp.name)}</strong></span>')
    parts.append(f'<span>{tp.filing_status.value.replace("_", " ").title()}</span>')
    parts.append(f'<span>Age {tp.age}</span>')
    if tp.dependents:
        parts.append(f'<span>{tp.num_dependents} dependent(s)</span>')
    parts.append("</div></section>")

    # Income summary
    income_rows = [
        _row_html("Wages (W-2)", inc.wages),
        _row_html("Interest (1099-INT)", inc.interest_income),
        _row_html("Dividend Income (1099-DIV)", inc.dividend_income),
        _row_html("Qualified Dividends", inc.qualified_dividends) if inc.qualified_dividends > 0 else "",
        _row_html("Capital Gains (1099-B/DIV)", inc.capital_gains),
        _row_html("Self-Employment (1099-NEC)", inc.self_employment_income),
        _row_html("Retirement (1099-R)", inc.retirement_income),
        _row_html("Net Rental (Schedule E)", inc.rental_income),
        _row_html("Other Income", inc.other_income),
    ]
    income_rows = [r for r in income_rows if r]
    income_rows.append(_row_html("TOTAL GROSS INCOME", inc.total_income, "report-row-total"))
    parts.append(_section_html("Income Summary", income_rows))

    # Federal
    fed = tax_return.federal_calculation
    if fed:
        fed_rows = [
            _row_html("Adjusted Gross Income", fed.adjusted_gross_income),
            _row_html("Deductions (" + fed.deduction_method + ")", fed.deductions),
            _row_html("Taxable Income", fed.taxable_income),
            _row_html("Tax Before Credits", fed.tax_before_credits),
            _row_html("Credits", fed.credits),
            _row_html("Tax After Credits", fed.tax_after_credits, "report-row-total"),
            _row_html("Withheld", fed.tax_withheld),
            _row_html("Estimated Payments", fed.estimated_payments) if fed.estimated_payments > 0 else "",
            _row_html("Total Payments", fed.total_payments),
        ]
        fed_rows = [r for r in fed_rows if r]
        refund = fed.refund_or_owed
        fed_rows.append(_row_html("Refund" if refund >= 0 else "Amount Owed", abs(refund),
                                  "report-row-highlight " + ("report-row-refund" if refund >= 0 else "report-row-owed")))
        parts.append(_section_html("Federal (Form 1040)", fed_rows))

    # State
    state = tax_return.state_calculation
    if state:
        st_rows = [
            _row_html("Taxable Income", state.taxable_income),
            _row_html("Tax After Credits", state.tax_after_credits),
            _row_html("Withheld", state.tax_withheld),
            _row_html("Estimated Payments", state.estimated_payments) if state.estimated_payments > 0 else "",
            _row_html("Total Payments", state.total_payments),
        ]
        st_rows = [r for r in st_rows if r]
        refund = state.refund_or_owed
        st_rows.append(_row_html("Refund" if refund >= 0 else "Amount Owed", abs(refund),
                                 "report-row-highlight " + ("report-row-refund" if refund >= 0 else "report-row-owed")))
        parts.append(_section_html(f"{state.jurisdiction} State", st_rows))

    # Combined
    if fed or state:
        total_tax = (fed.tax_after_credits if fed else 0) + (state.tax_after_credits if state else 0)
        fed_refund = fed.refund_or_owed if fed else 0
        state_refund = state.refund_or_owed if state else 0
        combined_rows = [
            _row_html("Federal Tax (after credits)", fed.tax_after_credits) if fed else "",
            _row_html((state.jurisdiction + " Tax (after credits)") if state else "", state.tax_after_credits) if state else "",
            _row_html("Combined Tax Liability", total_tax, "report-row-total"),
            _row_html("Federal Refund/Owed", fed_refund) if fed else "",
            _row_html(state.jurisdiction + " Refund/Owed", state_refund) if state else "",
        ]
        combined_rows = [r for r in combined_rows if r]
        net = fed_refund + state_refund
        combined_rows.append(_row_html("NET REFUND" if net >= 0 else "NET TAX OWED", abs(net),
                                       "report-row-highlight " + ("report-row-refund" if net >= 0 else "report-row-owed")))
        parts.append(_section_html("Combined Summary", combined_rows))

    # Capital loss carryover
    if hasattr(tax_return, "_capital_loss_carryover_applied") and tax_return._capital_loss_carryover_applied > 0:
        carry_rows = [
            _row_html("Prior year carryover applied", tax_return._capital_loss_carryover_applied),
            _row_html("Amount used this year", getattr(tax_return, "_capital_loss_deductible_used", 0)),
            _row_html("Remaining carryover", getattr(tax_return, "_capital_loss_carryover_remaining", 0)),
        ]
        parts.append(_section_html("Capital Loss Carryover", carry_rows))

    parts.append('<p class="report-disclaimer">This calculation is for reference only. Consult a tax professional for filing.</p>')
    parts.append("</div>")
    return "\n".join(parts)
