"""Test script for tax calculations."""

import sys
sys.path.insert(0, '.')

from src.models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits,
    TaxReturn, W2Data, Form1099Int
)
from src.federal_tax import FederalTaxCalculator
from src.california_tax import CaliforniaTaxCalculator


def test_federal_tax():
    """Test federal tax calculation."""
    print("=" * 50)
    print("Testing Federal Tax Calculation")
    print("=" * 50)

    calculator = FederalTaxCalculator(FilingStatus.SINGLE)

    # Test case: $100,000 taxable income
    income = TaxableIncome(wages=100000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result = calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        federal_withheld=15000
    )

    print(f"Gross Income: ${result.gross_income:,.2f}")
    print(f"Standard Deduction: ${result.deductions:,.2f}")
    print(f"Taxable Income: ${result.taxable_income:,.2f}")
    print(f"Federal Tax: ${result.tax_after_credits:,.2f}")
    print(f"Tax Withheld: ${result.tax_withheld:,.2f}")
    print(f"Refund/Owed: ${result.refund_or_owed:,.2f}")

    # Verify calculation manually
    # Taxable income = 100000 - 15000 = 85000
    # Tax = 11925*0.10 + (48475-11925)*0.12 + (85000-48475)*0.22
    #     = 1192.50 + 4386 + 8035.50 = 13614
    expected_taxable = 100000 - 15000  # 85000
    print(f"\nExpected taxable income: ${expected_taxable:,.2f}")

    return result


def test_california_tax():
    """Test California tax calculation."""
    print("\n" + "=" * 50)
    print("Testing California Tax Calculation")
    print("=" * 50)

    calculator = CaliforniaTaxCalculator(FilingStatus.SINGLE)

    income = TaxableIncome(wages=100000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result = calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        state_withheld=5000
    )

    print(f"Gross Income: ${result.gross_income:,.2f}")
    print(f"CA Standard Deduction: ${result.deductions:,.2f}")
    print(f"CA Taxable Income: ${result.taxable_income:,.2f}")
    print(f"CA Tax: ${result.tax_after_credits:,.2f}")
    print(f"State Tax Withheld: ${result.tax_withheld:,.2f}")
    print(f"Refund/Owed: ${result.refund_or_owed:,.2f}")

    return result


def test_full_return():
    """Test complete tax return with multiple income sources."""
    print("\n" + "=" * 50)
    print("Testing Complete Tax Return")
    print("=" * 50)

    # Create taxpayer
    taxpayer = TaxpayerInfo(
        name="Test User",
        filing_status=FilingStatus.SINGLE,
        age=30
    )

    # Create W-2
    w2 = W2Data(
        employer_name="Test Company",
        wages=85000,
        federal_withheld=12000,
        state_withheld=4500,
        social_security_wages=85000,
        medicare_wages=85000,
        state="CA"
    )

    # Create 1099-INT
    interest = Form1099Int(
        payer_name="Test Bank",
        interest_income=1500
    )

    # Build income
    income = TaxableIncome(
        wages=w2.wages,
        interest_income=interest.interest_income
    )

    print(f"\nIncome Sources:")
    print(f"  W-2 Wages: ${w2.wages:,.2f}")
    print(f"  Interest: ${interest.interest_income:,.2f}")
    print(f"  Total: ${income.total_income:,.2f}")

    # Calculate Federal
    fed_calc = FederalTaxCalculator(taxpayer.filing_status)
    fed_result = fed_calc.calculate(
        income=income,
        deductions=Deductions(use_standard=True),
        credits=TaxCredits(),
        federal_withheld=w2.federal_withheld
    )

    print(f"\nFederal Tax:")
    print(f"  Taxable Income: ${fed_result.taxable_income:,.2f}")
    print(f"  Tax Owed: ${fed_result.tax_after_credits:,.2f}")
    print(f"  Withheld: ${fed_result.tax_withheld:,.2f}")
    if fed_result.refund_or_owed >= 0:
        print(f"  REFUND: ${fed_result.refund_or_owed:,.2f}")
    else:
        print(f"  OWED: ${abs(fed_result.refund_or_owed):,.2f}")

    # Calculate California
    ca_calc = CaliforniaTaxCalculator(taxpayer.filing_status)
    ca_result = ca_calc.calculate(
        income=income,
        deductions=Deductions(use_standard=True),
        credits=TaxCredits(),
        state_withheld=w2.state_withheld
    )

    print(f"\nCalifornia Tax:")
    print(f"  Taxable Income: ${ca_result.taxable_income:,.2f}")
    print(f"  Tax Owed: ${ca_result.tax_after_credits:,.2f}")
    print(f"  Withheld: ${ca_result.tax_withheld:,.2f}")
    if ca_result.refund_or_owed >= 0:
        print(f"  REFUND: ${ca_result.refund_or_owed:,.2f}")
    else:
        print(f"  OWED: ${abs(ca_result.refund_or_owed):,.2f}")

    # Total
    total_refund = fed_result.refund_or_owed + ca_result.refund_or_owed
    print(f"\n{'='*30}")
    if total_refund >= 0:
        print(f"TOTAL REFUND: ${total_refund:,.2f}")
    else:
        print(f"TOTAL OWED: ${abs(total_refund):,.2f}")


def test_tax_brackets():
    """Test tax bracket calculations."""
    print("\n" + "=" * 50)
    print("Testing Tax Brackets")
    print("=" * 50)

    calculator = FederalTaxCalculator(FilingStatus.SINGLE)

    test_incomes = [25000, 50000, 100000, 200000, 500000]

    print(f"\n{'Taxable Income':>15} | {'Tax':>12} | {'Effective Rate':>14} | {'Marginal Rate':>13}")
    print("-" * 60)

    for taxable in test_incomes:
        tax, breakdown = calculator.calculate_progressive_tax(taxable)
        effective = (tax / taxable * 100) if taxable > 0 else 0
        marginal = calculator.calculate_marginal_rate(taxable) * 100

        print(f"${taxable:>14,} | ${tax:>11,.2f} | {effective:>13.2f}% | {marginal:>12.1f}%")


if __name__ == "__main__":
    test_federal_tax()
    test_california_tax()
    test_full_return()
    test_tax_brackets()

    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)
