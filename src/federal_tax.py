"""Federal tax calculation for tax year 2025."""

from typing import Tuple
from .models import (
    FilingStatus, TaxableIncome, Deductions, TaxCredits, TaxCalculation
)


# 2025 Federal Tax Brackets (estimated based on inflation adjustments)
# Format: (upper_limit, rate)
FEDERAL_TAX_BRACKETS_2025 = {
    FilingStatus.SINGLE: [
        (11_925, 0.10),
        (48_475, 0.12),
        (103_350, 0.22),
        (197_300, 0.24),
        (250_525, 0.32),
        (626_350, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (23_850, 0.10),
        (96_950, 0.12),
        (206_700, 0.22),
        (394_600, 0.24),
        (501_050, 0.32),
        (751_600, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (11_925, 0.10),
        (48_475, 0.12),
        (103_350, 0.22),
        (197_300, 0.24),
        (250_525, 0.32),
        (375_800, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (17_000, 0.10),
        (64_850, 0.12),
        (103_350, 0.22),
        (197_300, 0.24),
        (250_500, 0.32),
        (626_350, 0.35),
        (float('inf'), 0.37),
    ],
}

# 2025 Standard Deductions (estimated)
STANDARD_DEDUCTION_2025 = {
    FilingStatus.SINGLE: 15_000,
    FilingStatus.MARRIED_FILING_JOINTLY: 30_000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 15_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 22_500,
}

# Additional standard deduction for age 65+ or blind
ADDITIONAL_STANDARD_DEDUCTION_2025 = {
    FilingStatus.SINGLE: 1_950,
    FilingStatus.MARRIED_FILING_JOINTLY: 1_550,
    FilingStatus.MARRIED_FILING_SEPARATELY: 1_550,
    FilingStatus.HEAD_OF_HOUSEHOLD: 1_950,
}

# FICA tax rates
SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE_2025 = 176_100  # Estimated
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009  # For wages over threshold
ADDITIONAL_MEDICARE_THRESHOLD = {
    FilingStatus.SINGLE: 200_000,
    FilingStatus.MARRIED_FILING_JOINTLY: 250_000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 125_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 200_000,
}

# Self-employment tax rate
SELF_EMPLOYMENT_TAX_RATE = 0.153  # 12.4% SS + 2.9% Medicare


class FederalTaxCalculator:
    """Calculate federal income tax for tax year 2025."""

    def __init__(self, filing_status: FilingStatus = FilingStatus.SINGLE):
        """
        Initialize the federal tax calculator.

        Args:
            filing_status: The taxpayer's filing status
        """
        self.filing_status = filing_status
        self.brackets = FEDERAL_TAX_BRACKETS_2025[filing_status]
        self.standard_deduction = STANDARD_DEDUCTION_2025[filing_status]

    def get_standard_deduction(self, age: int = 30, is_blind: bool = False) -> float:
        """
        Get the standard deduction amount.

        Args:
            age: Taxpayer's age
            is_blind: Whether the taxpayer is legally blind

        Returns:
            Standard deduction amount
        """
        deduction = self.standard_deduction

        # Additional deduction for age 65+
        if age >= 65:
            deduction += ADDITIONAL_STANDARD_DEDUCTION_2025[self.filing_status]

        # Additional deduction for blindness
        if is_blind:
            deduction += ADDITIONAL_STANDARD_DEDUCTION_2025[self.filing_status]

        return deduction

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, list]:
        """
        Calculate tax using progressive brackets.

        Args:
            taxable_income: Income after deductions

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

    def calculate_self_employment_tax(self, self_employment_income: float) -> Tuple[float, float]:
        """
        Calculate self-employment tax.

        Args:
            self_employment_income: Net self-employment income

        Returns:
            Tuple of (SE tax, deductible portion)
        """
        if self_employment_income <= 0:
            return 0.0, 0.0

        # Calculate net SE earnings (92.35% of net SE income)
        net_se_earnings = self_employment_income * 0.9235

        # Social Security portion (up to wage base)
        ss_portion = min(net_se_earnings, SOCIAL_SECURITY_WAGE_BASE_2025)
        ss_tax = ss_portion * 0.124  # 12.4%

        # Medicare portion (all earnings)
        medicare_tax = net_se_earnings * 0.029  # 2.9%

        # Additional Medicare if over threshold
        threshold = ADDITIONAL_MEDICARE_THRESHOLD[self.filing_status]
        if net_se_earnings > threshold:
            medicare_tax += (net_se_earnings - threshold) * ADDITIONAL_MEDICARE_RATE

        total_se_tax = ss_tax + medicare_tax

        # Deductible portion is half of SE tax
        deductible = total_se_tax / 2

        return total_se_tax, deductible

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        federal_withheld: float,
        age: int = 30,
        is_blind: bool = False
    ) -> TaxCalculation:
        """
        Calculate complete federal tax liability.

        Args:
            income: Taxable income breakdown
            deductions: Deduction information
            credits: Tax credits
            federal_withheld: Total federal tax withheld
            age: Taxpayer's age
            is_blind: Whether taxpayer is legally blind

        Returns:
            Complete tax calculation result
        """
        # Calculate gross income
        gross_income = income.total_income

        # Calculate SE tax if applicable
        se_tax = 0.0
        se_deduction = 0.0
        if income.self_employment_income > 0:
            se_tax, se_deduction = self.calculate_self_employment_tax(
                income.self_employment_income
            )

        # Calculate adjustments (above-the-line deductions)
        adjustments = se_deduction

        # Calculate AGI
        agi = gross_income - adjustments

        # Determine deduction amount
        if deductions.use_standard:
            deductions.standard_deduction = self.get_standard_deduction(age, is_blind)
            deduction_amount = deductions.standard_deduction
        else:
            deduction_amount = deductions.itemized_deductions

        # Calculate taxable income
        taxable_income = max(0, agi - deduction_amount)

        # Calculate tax before credits
        tax_before_credits, _ = self.calculate_progressive_tax(taxable_income)

        # Add SE tax
        tax_before_credits += se_tax

        # Apply credits
        total_credits = credits.total_credits
        tax_after_credits = max(0, tax_before_credits - total_credits)

        return TaxCalculation(
            jurisdiction="Federal",
            gross_income=gross_income,
            adjustments=adjustments,
            adjusted_gross_income=agi,
            deductions=deduction_amount,
            taxable_income=taxable_income,
            tax_before_credits=tax_before_credits,
            credits=total_credits,
            tax_after_credits=tax_after_credits,
            tax_withheld=federal_withheld
        )

    def calculate_effective_rate(self, tax_calculation: TaxCalculation) -> float:
        """
        Calculate the effective tax rate.

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
        Determine the marginal tax rate for given taxable income.

        Args:
            taxable_income: Taxable income amount

        Returns:
            Marginal tax rate as decimal
        """
        previous_limit = 0
        for upper_limit, rate in self.brackets:
            if taxable_income <= upper_limit:
                return rate
            previous_limit = upper_limit
        return self.brackets[-1][1]  # Top rate


def calculate_federal_tax(
    filing_status: FilingStatus,
    income: TaxableIncome,
    deductions: Deductions,
    credits: TaxCredits,
    federal_withheld: float,
    age: int = 30,
    is_blind: bool = False
) -> TaxCalculation:
    """
    Convenience function to calculate federal tax.

    Args:
        filing_status: Filing status
        income: Income breakdown
        deductions: Deductions
        credits: Tax credits
        federal_withheld: Tax withheld
        age: Taxpayer age
        is_blind: Whether taxpayer is blind

    Returns:
        Tax calculation result
    """
    calculator = FederalTaxCalculator(filing_status)
    return calculator.calculate(
        income, deductions, credits, federal_withheld, age, is_blind
    )
