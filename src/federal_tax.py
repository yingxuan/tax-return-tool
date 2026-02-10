"""Federal tax calculation for tax years 2024 and 2025."""

from typing import Tuple, Optional
from .models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits,
    TaxCalculation, ScheduleAData, ScheduleAResult, ScheduleESummary,
)
from .schedule_a import ScheduleACalculator


# ---------------------------------------------------------------------------
# 2025 Federal Tax Brackets
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 2024 Federal Tax Brackets
# ---------------------------------------------------------------------------
FEDERAL_TAX_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (11_600, 0.10),
        (47_150, 0.12),
        (100_525, 0.22),
        (191_950, 0.24),
        (243_725, 0.32),
        (609_350, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (23_200, 0.10),
        (94_300, 0.12),
        (201_050, 0.22),
        (383_900, 0.24),
        (487_450, 0.32),
        (731_200, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (11_600, 0.10),
        (47_150, 0.12),
        (100_525, 0.22),
        (191_950, 0.24),
        (243_725, 0.32),
        (365_600, 0.35),
        (float('inf'), 0.37),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (16_550, 0.10),
        (63_100, 0.12),
        (100_500, 0.22),
        (191_950, 0.24),
        (243_700, 0.32),
        (609_350, 0.35),
        (float('inf'), 0.37),
    ],
}

# ---------------------------------------------------------------------------
# Standard Deductions
# ---------------------------------------------------------------------------
STANDARD_DEDUCTION = {
    2024: {
        FilingStatus.SINGLE: 14_600,
        FilingStatus.MARRIED_FILING_JOINTLY: 29_200,
        FilingStatus.MARRIED_FILING_SEPARATELY: 14_600,
        FilingStatus.HEAD_OF_HOUSEHOLD: 21_900,
    },
    2025: {
        FilingStatus.SINGLE: 15_000,
        FilingStatus.MARRIED_FILING_JOINTLY: 30_000,
        FilingStatus.MARRIED_FILING_SEPARATELY: 15_000,
        FilingStatus.HEAD_OF_HOUSEHOLD: 22_500,
    },
}

ADDITIONAL_STANDARD_DEDUCTION = {
    2024: {
        FilingStatus.SINGLE: 1_850,
        FilingStatus.MARRIED_FILING_JOINTLY: 1_550,
        FilingStatus.MARRIED_FILING_SEPARATELY: 1_550,
        FilingStatus.HEAD_OF_HOUSEHOLD: 1_850,
    },
    2025: {
        FilingStatus.SINGLE: 1_950,
        FilingStatus.MARRIED_FILING_JOINTLY: 1_550,
        FilingStatus.MARRIED_FILING_SEPARATELY: 1_550,
        FilingStatus.HEAD_OF_HOUSEHOLD: 1_950,
    },
}

# ---------------------------------------------------------------------------
# Child Tax Credit
# ---------------------------------------------------------------------------
CHILD_TAX_CREDIT_PER_CHILD = 2_000  # $2,000 per qualifying child under 17
# Phase-out thresholds for Child Tax Credit
CTC_PHASEOUT = {
    FilingStatus.SINGLE: 200_000,
    FilingStatus.MARRIED_FILING_JOINTLY: 400_000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 200_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 200_000,
}
CTC_PHASEOUT_RATE = 0.05  # $50 reduction per $1,000 over threshold

# ---------------------------------------------------------------------------
# FICA / Self-Employment
# ---------------------------------------------------------------------------
SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE = {2024: 168_600, 2025: 176_100}
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = {
    FilingStatus.SINGLE: 200_000,
    FilingStatus.MARRIED_FILING_JOINTLY: 250_000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 125_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 200_000,
}
SELF_EMPLOYMENT_TAX_RATE = 0.153


def _get_brackets(tax_year: int, filing_status: FilingStatus):
    if tax_year == 2024:
        return FEDERAL_TAX_BRACKETS_2024[filing_status]
    return FEDERAL_TAX_BRACKETS_2025[filing_status]


class FederalTaxCalculator:
    """Calculate federal income tax for tax year 2024 or 2025."""

    def __init__(
        self,
        filing_status: FilingStatus = FilingStatus.SINGLE,
        tax_year: int = 2025,
    ):
        self.filing_status = filing_status
        self.tax_year = tax_year
        self.brackets = _get_brackets(tax_year, filing_status)

        std = STANDARD_DEDUCTION.get(tax_year, STANDARD_DEDUCTION[2025])
        self.standard_deduction = std[filing_status]

    def get_standard_deduction(self, age: int = 30, is_blind: bool = False) -> float:
        """Get the standard deduction, including additional amounts for age/blindness."""
        deduction = self.standard_deduction
        add = ADDITIONAL_STANDARD_DEDUCTION.get(
            self.tax_year, ADDITIONAL_STANDARD_DEDUCTION[2025]
        )
        if age >= 65:
            deduction += add[self.filing_status]
        if is_blind:
            deduction += add[self.filing_status]
        return deduction

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, list]:
        """Calculate tax using progressive brackets. Returns (total_tax, breakdown)."""
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
                label = (
                    f"${previous_limit:,.0f} - ${upper_limit:,.0f}"
                    if upper_limit != float('inf')
                    else f"${previous_limit:,.0f}+"
                )
                breakdown.append({
                    'bracket': label,
                    'rate': rate,
                    'income': bracket_income,
                    'tax': bracket_tax,
                })
            previous_limit = upper_limit

        return total_tax, breakdown

    def calculate_self_employment_tax(
        self, self_employment_income: float
    ) -> Tuple[float, float]:
        """Calculate SE tax. Returns (se_tax, deductible_half)."""
        if self_employment_income <= 0:
            return 0.0, 0.0

        net_se_earnings = self_employment_income * 0.9235
        ss_base = SOCIAL_SECURITY_WAGE_BASE.get(
            self.tax_year, SOCIAL_SECURITY_WAGE_BASE[2025]
        )
        ss_portion = min(net_se_earnings, ss_base)
        ss_tax = ss_portion * 0.124

        medicare_tax = net_se_earnings * 0.029
        threshold = ADDITIONAL_MEDICARE_THRESHOLD[self.filing_status]
        if net_se_earnings > threshold:
            medicare_tax += (net_se_earnings - threshold) * ADDITIONAL_MEDICARE_RATE

        total_se_tax = ss_tax + medicare_tax
        return total_se_tax, total_se_tax / 2

    def calculate_additional_medicare_tax(self, wages: float) -> float:
        """Calculate 0.9% Additional Medicare Tax on W-2 wages exceeding threshold."""
        threshold = ADDITIONAL_MEDICARE_THRESHOLD[self.filing_status]
        if wages > threshold:
            return (wages - threshold) * ADDITIONAL_MEDICARE_RATE
        return 0.0

    def calculate_child_tax_credit(
        self, num_qualifying_children: int, agi: float
    ) -> float:
        """
        Calculate Child Tax Credit.

        $2,000 per qualifying child under 17, phased out at higher incomes.
        """
        if num_qualifying_children <= 0:
            return 0.0

        base_credit = num_qualifying_children * CHILD_TAX_CREDIT_PER_CHILD
        threshold = CTC_PHASEOUT[self.filing_status]

        if agi > threshold:
            # Reduce by $50 for each $1,000 (or fraction) over threshold
            excess = agi - threshold
            reduction = int((excess + 999) / 1000) * 50
            base_credit = max(0, base_credit - reduction)

        return base_credit

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        federal_withheld: float,
        age: int = 30,
        is_blind: bool = False,
        num_qualifying_children: int = 0,
        schedule_a_data: Optional[ScheduleAData] = None,
        schedule_e_summary: Optional[ScheduleESummary] = None,
        estimated_payments: float = 0.0,
    ) -> TaxCalculation:
        """
        Calculate complete federal tax liability (Form 1040).

        Args:
            income: Taxable income breakdown.
            deductions: Deduction information.
            credits: Tax credits.
            federal_withheld: Total federal tax withheld.
            age: Taxpayer's age.
            is_blind: Whether taxpayer is legally blind.
            num_qualifying_children: Number of children under 17.
            schedule_a_data: Itemized deduction inputs (if any).
            schedule_e_summary: Pre-computed Schedule E rental summary.
            estimated_payments: Total federal estimated tax payments.

        Returns:
            Complete TaxCalculation result.
        """
        # --- Gross Income (Form 1040 Lines 1-9) ---
        gross_income = income.total_income

        # --- Self-Employment Tax ---
        se_tax = 0.0
        se_deduction = 0.0
        if income.self_employment_income > 0:
            se_tax, se_deduction = self.calculate_self_employment_tax(
                income.self_employment_income
            )

        # --- Adjustments (above-the-line, Line 10) ---
        adjustments = se_deduction

        # --- AGI (Line 11) ---
        agi = gross_income - adjustments

        # --- Deductions (Line 12-13) ---
        std_deduction = self.get_standard_deduction(age, is_blind)
        schedule_a_result = None

        if schedule_a_data:
            # Compute itemized deductions and compare
            sched_a_calc = ScheduleACalculator(
                filing_status=self.filing_status,
                standard_deduction=std_deduction,
            )
            schedule_a_result = sched_a_calc.calculate(schedule_a_data, agi)
            deduction_amount = schedule_a_result.deduction_amount
            deduction_method = "itemized" if schedule_a_result.use_itemized else "standard"
        elif not deductions.use_standard:
            deduction_amount = deductions.itemized_deductions
            deduction_method = "itemized"
        else:
            deduction_amount = std_deduction
            deduction_method = "standard"

        # --- Taxable Income (Line 15) ---
        taxable_income = max(0, agi - deduction_amount)

        # --- Tax (Line 16) ---
        income_tax, bracket_breakdown = self.calculate_progressive_tax(taxable_income)

        # Additional Medicare Tax on W-2 wages (0.9% over threshold)
        additional_medicare = self.calculate_additional_medicare_tax(income.wages)

        # Add SE tax (this goes on Schedule SE / Line 23)
        tax_before_credits = income_tax + se_tax + additional_medicare

        # --- Credits (Lines 19-21) ---
        # Child Tax Credit
        ctc = self.calculate_child_tax_credit(num_qualifying_children, agi)
        total_credits = credits.total_credits + ctc

        # Tax after credits
        tax_after_credits = max(0, tax_before_credits - total_credits)

        return TaxCalculation(
            jurisdiction="Federal",
            tax_year=self.tax_year,
            gross_income=round(gross_income, 2),
            adjustments=round(adjustments, 2),
            adjusted_gross_income=round(agi, 2),
            deductions=round(deduction_amount, 2),
            taxable_income=round(taxable_income, 2),
            tax_before_credits=round(tax_before_credits, 2),
            credits=round(total_credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            tax_withheld=round(federal_withheld, 2),
            estimated_payments=round(estimated_payments, 2),
            self_employment_tax=round(se_tax, 2),
            additional_medicare_tax=round(additional_medicare, 2),
            deduction_method=deduction_method,
            bracket_breakdown=bracket_breakdown,
            schedule_e_summary=schedule_e_summary,
            schedule_a_result=schedule_a_result,
            child_tax_credit=round(ctc, 2),
            num_qualifying_children=num_qualifying_children,
        )

    def calculate_effective_rate(self, tax_calculation: TaxCalculation) -> float:
        if tax_calculation.gross_income <= 0:
            return 0.0
        return tax_calculation.tax_after_credits / tax_calculation.gross_income

    def calculate_marginal_rate(self, taxable_income: float) -> float:
        previous_limit = 0
        for upper_limit, rate in self.brackets:
            if taxable_income <= upper_limit:
                return rate
            previous_limit = upper_limit
        return self.brackets[-1][1]


def calculate_federal_tax(
    filing_status: FilingStatus,
    income: TaxableIncome,
    deductions: Deductions,
    credits: TaxCredits,
    federal_withheld: float,
    age: int = 30,
    is_blind: bool = False,
    tax_year: int = 2025,
    num_qualifying_children: int = 0,
    schedule_a_data: Optional[ScheduleAData] = None,
    schedule_e_summary: Optional[ScheduleESummary] = None,
    estimated_payments: float = 0.0,
) -> TaxCalculation:
    """Convenience function to calculate federal tax."""
    calculator = FederalTaxCalculator(filing_status, tax_year)
    return calculator.calculate(
        income, deductions, credits, federal_withheld, age, is_blind,
        num_qualifying_children, schedule_a_data, schedule_e_summary,
        estimated_payments,
    )
