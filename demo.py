"""Standalone demo script - no external dependencies required."""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class FilingStatus(Enum):
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"


# 2025 Federal Tax Brackets
FEDERAL_BRACKETS_SINGLE = [
    (11_925, 0.10),
    (48_475, 0.12),
    (103_350, 0.22),
    (197_300, 0.24),
    (250_525, 0.32),
    (626_350, 0.35),
    (float('inf'), 0.37),
]

# 2025 California Tax Brackets
CA_BRACKETS_SINGLE = [
    (10_756, 0.01),
    (25_499, 0.02),
    (40_245, 0.04),
    (55_866, 0.06),
    (70_606, 0.08),
    (360_659, 0.093),
    (432_787, 0.103),
    (721_314, 0.113),
    (float('inf'), 0.123),
]

FEDERAL_STANDARD_DEDUCTION = 15_000
CA_STANDARD_DEDUCTION = 5_540
CA_EXEMPTION_CREDIT = 144


def calculate_tax(taxable_income: float, brackets: list) -> Tuple[float, list]:
    """Calculate tax using progressive brackets."""
    if taxable_income <= 0:
        return 0.0, []

    total_tax = 0.0
    breakdown = []
    previous_limit = 0

    for upper_limit, rate in brackets:
        if taxable_income <= previous_limit:
            break

        bracket_income = min(taxable_income, upper_limit) - previous_limit
        if bracket_income > 0:
            bracket_tax = bracket_income * rate
            total_tax += bracket_tax
            breakdown.append({
                'range': f"${previous_limit:,} - ${upper_limit:,}" if upper_limit != float('inf') else f"${previous_limit:,}+",
                'rate': f"{rate*100:.1f}%",
                'income': bracket_income,
                'tax': bracket_tax
            })

        previous_limit = upper_limit

    return total_tax, breakdown


def format_currency(amount: float) -> str:
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def run_demo():
    print("\n" + "=" * 60)
    print("           TAX RETURN CALCULATOR DEMO")
    print("                  Tax Year 2025")
    print("=" * 60)

    # Sample data
    wages = 120_000.00
    interest_income = 1_500.00
    dividend_income = 3_000.00
    federal_withheld = 18_500.00
    state_withheld = 7_200.00

    total_income = wages + interest_income + dividend_income

    print(f"\nTaxpayer: John Doe")
    print(f"Filing Status: Single")

    # Income Summary
    print("\n" + "-" * 40)
    print("INCOME SUMMARY")
    print("-" * 40)
    print(f"  W-2 Wages:              {format_currency(wages):>15}")
    print(f"  Interest Income:        {format_currency(interest_income):>15}")
    print(f"  Dividend Income:        {format_currency(dividend_income):>15}")
    print("-" * 40)
    print(f"  TOTAL GROSS INCOME:     {format_currency(total_income):>15}")

    # Federal Tax Calculation
    print("\n" + "-" * 40)
    print("FEDERAL TAX CALCULATION")
    print("-" * 40)

    fed_agi = total_income
    fed_taxable = fed_agi - FEDERAL_STANDARD_DEDUCTION
    fed_tax, fed_breakdown = calculate_tax(fed_taxable, FEDERAL_BRACKETS_SINGLE)

    print(f"  Adjusted Gross Income:  {format_currency(fed_agi):>15}")
    print(f"  Standard Deduction:     {format_currency(FEDERAL_STANDARD_DEDUCTION):>15}")
    print(f"  Taxable Income:         {format_currency(fed_taxable):>15}")

    print("\n  Tax Bracket Breakdown:")
    for b in fed_breakdown:
        print(f"    {b['range']:25} @ {b['rate']:>5} = ${b['tax']:>10,.2f}")

    print(f"\n  Federal Tax:            {format_currency(fed_tax):>15}")
    print(f"  Federal Withheld:       {format_currency(federal_withheld):>15}")

    fed_refund = federal_withheld - fed_tax
    if fed_refund >= 0:
        print(f"  FEDERAL REFUND:         {format_currency(fed_refund):>15}")
    else:
        print(f"  FEDERAL OWED:           {format_currency(abs(fed_refund)):>15}")

    # California Tax Calculation
    print("\n" + "-" * 40)
    print("CALIFORNIA TAX CALCULATION")
    print("-" * 40)

    ca_agi = total_income
    ca_taxable = ca_agi - CA_STANDARD_DEDUCTION
    ca_tax_before_credits, ca_breakdown = calculate_tax(ca_taxable, CA_BRACKETS_SINGLE)
    ca_tax = max(0, ca_tax_before_credits - CA_EXEMPTION_CREDIT)

    print(f"  CA Adjusted Gross Income: {format_currency(ca_agi):>13}")
    print(f"  CA Standard Deduction:    {format_currency(CA_STANDARD_DEDUCTION):>13}")
    print(f"  CA Taxable Income:        {format_currency(ca_taxable):>13}")

    print("\n  CA Tax Bracket Breakdown:")
    for b in ca_breakdown:
        print(f"    {b['range']:25} @ {b['rate']:>5} = ${b['tax']:>10,.2f}")

    print(f"\n  CA Tax Before Credits:    {format_currency(ca_tax_before_credits):>13}")
    print(f"  CA Exemption Credit:      {format_currency(CA_EXEMPTION_CREDIT):>13}")
    print(f"  CA Tax After Credits:     {format_currency(ca_tax):>13}")
    print(f"  State Withheld:           {format_currency(state_withheld):>13}")

    ca_refund = state_withheld - ca_tax
    if ca_refund >= 0:
        print(f"  CA REFUND:                {format_currency(ca_refund):>13}")
    else:
        print(f"  CA OWED:                  {format_currency(abs(ca_refund)):>13}")

    # Total Summary
    print("\n" + "=" * 40)
    print("TOTAL SUMMARY")
    print("=" * 40)

    total_tax = fed_tax + ca_tax
    total_withheld = federal_withheld + state_withheld
    total_refund = total_withheld - total_tax

    print(f"  Total Tax Liability:    {format_currency(total_tax):>15}")
    print(f"  Total Withheld:         {format_currency(total_withheld):>15}")

    if total_refund >= 0:
        print(f"  TOTAL REFUND:           {format_currency(total_refund):>15}")
    else:
        print(f"  TOTAL TAX OWED:         {format_currency(abs(total_refund)):>15}")

    print("\n" + "=" * 60)

    # Effective tax rates
    fed_effective = (fed_tax / total_income) * 100
    ca_effective = (ca_tax / total_income) * 100
    total_effective = (total_tax / total_income) * 100

    print("\nEFFECTIVE TAX RATES:")
    print(f"  Federal:     {fed_effective:.2f}%")
    print(f"  California:  {ca_effective:.2f}%")
    print(f"  Combined:    {total_effective:.2f}%")

    print("\n" + "-" * 60)
    print("NOTE: This is a simplified calculation for demonstration.")
    print("Actual tax liability may vary. Consult a tax professional.")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    run_demo()
