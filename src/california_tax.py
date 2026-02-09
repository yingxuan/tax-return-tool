"""California state tax calculation for tax year 2025."""

from typing import Tuple
from .models import (
    FilingStatus, TaxableIncome, Deductions, TaxCredits, TaxCalculation
)


# 2025 California Tax Brackets (estimated based on inflation adjustments)
# California uses different bracket names but we map to federal status
CA_TAX_BRACKETS_2025 = {
    FilingStatus.SINGLE: [
        (10_756, 0.01),
        (25_499, 0.02),
        (40_245, 0.04),
        (55_866, 0.06),
        (70_606, 0.08),
        (360_659, 0.093),
        (432_787, 0.103),
        (721_314, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (21_512, 0.01),
        (50_998, 0.02),
        (80_490, 0.04),
        (111_732, 0.06),
        (141_212, 0.08),
        (721_318, 0.093),
        (865_574, 0.103),
        (1_442_628, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (10_756, 0.01),
        (25_499, 0.02),
        (40_245, 0.04),
        (55_866, 0.06),
        (70_606, 0.08),
        (360_659, 0.093),
        (432_787, 0.103),
        (721_314, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (21_512, 0.01),
        (50_998, 0.02),
        (65_744, 0.04),
        (81_364, 0.06),
        (96_107, 0.08),
        (490_493, 0.093),
        (588_593, 0.103),
        (980_987, 0.113),
        (float('inf'), 0.123),
    ],
}

# 2025 California Standard Deductions (estimated)
CA_STANDARD_DEDUCTION_2025 = {
    FilingStatus.SINGLE: 5_540,
    FilingStatus.MARRIED_FILING_JOINTLY: 11_080,
    FilingStatus.MARRIED_FILING_SEPARATELY: 5_540,
    FilingStatus.HEAD_OF_HOUSEHOLD: 11_080,
}

# California Exemption Credits (per exemption)
CA_EXEMPTION_CREDIT_2025 = 144  # Per personal exemption

# California Mental Health Services Tax (Prop 63)
# Additional 1% tax on taxable income over $1 million
CA_MENTAL_HEALTH_THRESHOLD = 1_000_000
CA_MENTAL_HEALTH_RATE = 0.01

# California SDI (State Disability Insurance) rate
CA_SDI_RATE = 0.009
CA_SDI_WAGE_BASE_2025 = 153_164  # Estimated


class CaliforniaTaxCalculator:
    """Calculate California state income tax for tax year 2025."""

    def __init__(self, filing_status: FilingStatus = FilingStatus.SINGLE):
        """
        Initialize the California tax calculator.

        Args:
            filing_status: The taxpayer's filing status
        """
        self.filing_status = filing_status
        self.brackets = CA_TAX_BRACKETS_2025[filing_status]
        self.standard_deduction = CA_STANDARD_DEDUCTION_2025[filing_status]

    def get_standard_deduction(self) -> float:
        """
        Get the California standard deduction amount.

        Returns:
            Standard deduction amount
        """
        return self.standard_deduction

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, list]:
        """
        Calculate California tax using progressive brackets.

        Args:
            taxable_income: California taxable income

        Returns:
            Tuple of (total tax, breakdown by bracket)
        """
        if taxable_income <= 0:
            return 0.0, []

        total_tax = 0.0
        breakdown = []
        previous_limit = 0

        for upper_limit, rate in self.brackets:
            if taxable_income <= previous_limit:
                break

            bracket_income = min(taxable_income, upper_limit) - previous_limit
            if bracket_income > 0:
                bracket_tax = bracket_income * rate
                total_tax += bracket_tax
                breakdown.append({
                    'bracket': f"${previous_limit:,.0f} - ${upper_limit:,.0f}" if upper_limit != float('inf') else f"${previous_limit:,.0f}+",
                    'rate': rate,
                    'income': bracket_income,
                    'tax': bracket_tax
                })

            previous_limit = upper_limit

        return total_tax, breakdown

    def calculate_mental_health_tax(self, taxable_income: float) -> float:
        """
        Calculate the Mental Health Services Tax (Prop 63).

        Args:
            taxable_income: California taxable income

        Returns:
            Additional mental health tax amount
        """
        if taxable_income > CA_MENTAL_HEALTH_THRESHOLD:
            return (taxable_income - CA_MENTAL_HEALTH_THRESHOLD) * CA_MENTAL_HEALTH_RATE
        return 0.0

    def calculate_exemption_credit(self, num_exemptions: int = 1) -> float:
        """
        Calculate the California exemption credit.

        Args:
            num_exemptions: Number of exemptions to claim

        Returns:
            Total exemption credit amount
        """
        return CA_EXEMPTION_CREDIT_2025 * num_exemptions

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        state_withheld: float,
        num_exemptions: int = 1
    ) -> TaxCalculation:
        """
        Calculate complete California tax liability.

        Args:
            income: Taxable income breakdown
            deductions: Deduction information
            credits: Tax credits (California-specific credits)
            state_withheld: Total state tax withheld
            num_exemptions: Number of exemptions

        Returns:
            Complete California tax calculation result
        """
        # California starts with federal AGI
        # For simplicity, we'll use gross income minus SE deduction
        gross_income = income.total_income

        # California adjustments (similar to federal)
        adjustments = 0.0
        if income.self_employment_income > 0:
            # California allows same SE tax deduction as federal
            se_tax = income.self_employment_income * 0.9235 * 0.153
            adjustments = se_tax / 2

        # California AGI
        ca_agi = gross_income - adjustments

        # Determine deduction amount
        # California has its own standard deduction
        if deductions.use_standard:
            deduction_amount = self.get_standard_deduction()
        else:
            # California itemized deductions differ from federal
            # SALT deduction is not limited in California
            ca_itemized = (
                deductions.state_local_taxes +  # No $10K cap in CA
                deductions.mortgage_interest +
                deductions.charitable_contributions +
                deductions.medical_expenses
            )
            deduction_amount = max(ca_itemized, self.get_standard_deduction())

        # Calculate California taxable income
        taxable_income = max(0, ca_agi - deduction_amount)

        # Calculate base tax
        base_tax, _ = self.calculate_progressive_tax(taxable_income)

        # Add Mental Health Services Tax if applicable
        mental_health_tax = self.calculate_mental_health_tax(taxable_income)
        tax_before_credits = base_tax + mental_health_tax

        # Apply California credits
        exemption_credit = self.calculate_exemption_credit(num_exemptions)
        total_credits = credits.total_credits + exemption_credit

        # Tax after credits (cannot go below zero)
        tax_after_credits = max(0, tax_before_credits - total_credits)

        return TaxCalculation(
            jurisdiction="California",
            gross_income=gross_income,
            adjustments=adjustments,
            adjusted_gross_income=ca_agi,
            deductions=deduction_amount,
            taxable_income=taxable_income,
            tax_before_credits=tax_before_credits,
            credits=total_credits,
            tax_after_credits=tax_after_credits,
            tax_withheld=state_withheld
        )

    def calculate_effective_rate(self, tax_calculation: TaxCalculation) -> float:
        """
        Calculate the effective California tax rate.

        Args:
            tax_calculation: Completed tax calculation

        Returns:
            Effective tax rate as decimal
        """
        if tax_calculation.gross_income <= 0:
            return 0.0
        return tax_calculation.tax_after_credits / tax_calculation.gross_income

    def calculate_marginal_rate(self, taxable_income: float) -> float:
        """
        Determine the marginal California tax rate.

        Args:
            taxable_income: California taxable income

        Returns:
            Marginal tax rate as decimal
        """
        for upper_limit, rate in self.brackets:
            if taxable_income <= upper_limit:
                return rate
        return self.brackets[-1][1]  # Top rate


def calculate_california_tax(
    filing_status: FilingStatus,
    income: TaxableIncome,
    deductions: Deductions,
    credits: TaxCredits,
    state_withheld: float,
    num_exemptions: int = 1
) -> TaxCalculation:
    """
    Convenience function to calculate California tax.

    Args:
        filing_status: Filing status
        income: Income breakdown
        deductions: Deductions
        credits: Tax credits
        state_withheld: State tax withheld
        num_exemptions: Number of exemptions

    Returns:
        Tax calculation result
    """
    calculator = CaliforniaTaxCalculator(filing_status)
    return calculator.calculate(
        income, deductions, credits, state_withheld, num_exemptions
    )


def calculate_sdi(wages: float) -> float:
    """
    Calculate California State Disability Insurance.

    Args:
        wages: Total wages subject to SDI

    Returns:
        SDI amount
    """
    taxable_wages = min(wages, CA_SDI_WAGE_BASE_2025)
    return taxable_wages * CA_SDI_RATE
