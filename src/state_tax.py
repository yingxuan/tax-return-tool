"""
State income tax calculation dispatcher and state-specific calculators.

Supports California (Form 540), New York (IT-201), and other states with
progressive brackets. No-income-tax states return None.
"""

from typing import Optional, Tuple, List
from .models import (
    FilingStatus,
    TaxableIncome,
    Deductions,
    TaxCredits,
    TaxCalculation,
    ScheduleAData,
    ScheduleAResult,
    ScheduleESummary,
)
from .config_loader import STATES_NO_INCOME_TAX


# ---------------------------------------------------------------------------
# New York State (IT-201) - 2024 and 2025 brackets
# Source: NY tax.ny.gov tax tables
# ---------------------------------------------------------------------------
NY_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (8_500, 0.04),
        (11_700, 0.045),
        (13_900, 0.0525),
        (80_650, 0.055),
        (215_400, 0.06),
        (1_077_550, 0.0685),
        (5_000_000, 0.0965),
        (25_000_000, 0.103),
        (float("inf"), 0.109),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (17_150, 0.04),
        (23_600, 0.045),
        (27_900, 0.0525),
        (161_550, 0.055),
        (323_200, 0.06),
        (2_155_350, 0.0685),
        (5_000_000, 0.0965),
        (25_000_000, 0.103),
        (float("inf"), 0.109),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (8_500, 0.04),
        (11_700, 0.045),
        (13_900, 0.0525),
        (80_650, 0.055),
        (215_400, 0.06),
        (1_077_550, 0.0685),
        (5_000_000, 0.0965),
        (25_000_000, 0.103),
        (float("inf"), 0.109),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (12_800, 0.04),
        (17_650, 0.045),
        (20_900, 0.0525),
        (107_650, 0.055),
        (269_300, 0.06),
        (1_616_450, 0.0685),
        (5_000_000, 0.0965),
        (25_000_000, 0.103),
        (float("inf"), 0.109),
    ],
}

NY_BRACKETS_2025 = NY_BRACKETS_2024  # Same brackets for 2025

NY_STANDARD_DEDUCTION = {
    2024: {
        FilingStatus.SINGLE: 8_000,
        FilingStatus.MARRIED_FILING_JOINTLY: 15_800,
        FilingStatus.MARRIED_FILING_SEPARATELY: 8_000,
        FilingStatus.HEAD_OF_HOUSEHOLD: 11_200,
    },
    2025: {
        FilingStatus.SINGLE: 8_000,
        FilingStatus.MARRIED_FILING_JOINTLY: 16_050,
        FilingStatus.MARRIED_FILING_SEPARATELY: 8_000,
        FilingStatus.HEAD_OF_HOUSEHOLD: 11_200,
    },
}


class NewYorkTaxCalculator:
    """Calculate New York state income tax (Form IT-201). Simplified: no NYC resident tax."""

    def __init__(
        self,
        filing_status: FilingStatus = FilingStatus.SINGLE,
        tax_year: int = 2025,
    ):
        self.filing_status = filing_status
        self.tax_year = tax_year
        brackets = NY_BRACKETS_2024 if tax_year == 2024 else NY_BRACKETS_2025
        self.brackets = brackets.get(filing_status, brackets[FilingStatus.SINGLE])
        std = NY_STANDARD_DEDUCTION.get(tax_year, NY_STANDARD_DEDUCTION[2025])
        self.standard_deduction = std.get(filing_status, std[FilingStatus.SINGLE])

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, List[dict]]:
        if taxable_income <= 0:
            return 0.0, []
        total_tax = 0.0
        breakdown = []
        previous_limit = 0.0
        for upper_limit, rate in self.brackets:
            if taxable_income <= previous_limit:
                break
            bracket_income = min(taxable_income, upper_limit) - previous_limit
            if bracket_income > 0:
                bracket_tax = bracket_income * rate
                total_tax += bracket_tax
                label = (
                    f"${previous_limit:,.0f}+" if upper_limit == float("inf") else
                    f"${previous_limit:,.0f} - ${upper_limit:,.0f}"
                )
                breakdown.append({
                    "bracket": label,
                    "rate": rate,
                    "income": bracket_income,
                    "tax": bracket_tax,
                })
            previous_limit = upper_limit
        return total_tax, breakdown

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        state_withheld: float,
        num_exemptions: int = 1,
        is_renter: bool = False,
        schedule_a_data: Optional[ScheduleAData] = None,
        schedule_e_summary: Optional[ScheduleESummary] = None,
        estimated_payments: float = 0.0,
        us_treasury_interest: float = 0.0,
        federal_agi: float = 0.0,
    ) -> TaxCalculation:
        """NY taxable income starts from federal-style AGI; NY allows itemized or standard."""
        gross_income = income.total_income - us_treasury_interest
        adjustments = 0.0
        ny_agi = gross_income - adjustments

        deduction_amount = self.standard_deduction
        deduction_method = "standard"
        schedule_a_result = None

        if schedule_a_data:
            from .schedule_a import ScheduleACalculator
            # NY itemized: similar to federal but NY-specific adjustments; use simplified comparison
            ny_std = self.standard_deduction
            # For simplicity: use federal itemized total if available and compare to NY standard
            if schedule_a_data.real_estate_taxes + schedule_a_data.mortgage_interest + schedule_a_data.cash_contributions > ny_std:
                deduction_amount = (
                    min(schedule_a_data.real_estate_taxes, 10_000)  # SALT cap
                    + schedule_a_data.mortgage_interest
                    + schedule_a_data.cash_contributions
                )
                deduction_method = "itemized"
            else:
                deduction_amount = ny_std

        taxable_income = max(0, ny_agi - deduction_amount)
        base_tax, bracket_breakdown = self.calculate_progressive_tax(taxable_income)
        tax_before_credits = base_tax
        total_credits = credits.total_credits
        tax_after_credits = max(0, tax_before_credits - total_credits)

        return TaxCalculation(
            jurisdiction="New York",
            tax_year=self.tax_year,
            gross_income=round(gross_income, 2),
            adjustments=round(adjustments, 2),
            adjusted_gross_income=round(ny_agi, 2),
            deductions=round(deduction_amount, 2),
            taxable_income=round(taxable_income, 2),
            tax_before_credits=round(tax_before_credits, 2),
            credits=round(total_credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            tax_withheld=round(state_withheld, 2),
            estimated_payments=round(estimated_payments, 2),
            deduction_method=deduction_method,
            bracket_breakdown=bracket_breakdown,
            schedule_a_result=schedule_a_result,
        )


# ---------------------------------------------------------------------------
# New Jersey (NJ-1040) - 2024/2025 brackets (Gross Income Tax)
# Source: NJ Treasury tax tables
# ---------------------------------------------------------------------------
NJ_BRACKETS = {
    FilingStatus.SINGLE: [
        (20_000, 0.014),
        (35_000, 0.0175),
        (40_000, 0.035),
        (75_000, 0.05525),
        (500_000, 0.0637),
        (1_000_000, 0.0897),
        (float("inf"), 0.1075),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (20_000, 0.014),
        (50_000, 0.0175),
        (70_000, 0.0245),
        (80_000, 0.035),
        (150_000, 0.05525),
        (500_000, 0.0637),
        (1_000_000, 0.0897),
        (float("inf"), 0.1075),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (20_000, 0.014),
        (35_000, 0.0175),
        (40_000, 0.035),
        (75_000, 0.05525),
        (500_000, 0.0637),
        (1_000_000, 0.0897),
        (float("inf"), 0.1075),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (20_000, 0.014),
        (50_000, 0.0175),
        (70_000, 0.0245),
        (80_000, 0.035),
        (150_000, 0.05525),
        (500_000, 0.0637),
        (1_000_000, 0.0897),
        (float("inf"), 0.1075),
    ],
}
# NJ filing threshold: no tax below this; use as standard deduction for simplicity
NJ_STANDARD_DEDUCTION = {
    FilingStatus.SINGLE: 10_000,
    FilingStatus.MARRIED_FILING_JOINTLY: 20_000,
    FilingStatus.MARRIED_FILING_SEPARATELY: 10_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 20_000,
}


class NewJerseyTaxCalculator:
    """Calculate New Jersey Gross Income Tax (NJ-1040). Simplified."""

    def __init__(self, filing_status: FilingStatus = FilingStatus.SINGLE, tax_year: int = 2025):
        self.filing_status = filing_status
        self.tax_year = tax_year
        self.brackets = NJ_BRACKETS.get(filing_status, NJ_BRACKETS[FilingStatus.SINGLE])
        self.standard_deduction = NJ_STANDARD_DEDUCTION.get(filing_status, 10_000)

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, List[dict]]:
        if taxable_income <= 0:
            return 0.0, []
        total_tax = 0.0
        breakdown = []
        prev = 0.0
        for upper, rate in self.brackets:
            if taxable_income <= prev:
                break
            amt = min(taxable_income, upper) - prev
            if amt > 0:
                tax = amt * rate
                total_tax += tax
                label = f"${prev:,.0f}+" if upper == float("inf") else f"${prev:,.0f} - ${upper:,.0f}"
                breakdown.append({"bracket": label, "rate": rate, "income": amt, "tax": tax})
            prev = upper
        return total_tax, breakdown

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        state_withheld: float,
        num_exemptions: int = 1,
        is_renter: bool = False,
        schedule_a_data: Optional[ScheduleAData] = None,
        schedule_e_summary: Optional[ScheduleESummary] = None,
        estimated_payments: float = 0.0,
        us_treasury_interest: float = 0.0,
        federal_agi: float = 0.0,
    ) -> TaxCalculation:
        gross_income = income.total_income - us_treasury_interest
        taxable_income = max(0, gross_income - self.standard_deduction)
        base_tax, bracket_breakdown = self.calculate_progressive_tax(taxable_income)
        tax_after_credits = max(0, base_tax - credits.total_credits)
        return TaxCalculation(
            jurisdiction="New Jersey",
            tax_year=self.tax_year,
            gross_income=round(gross_income, 2),
            adjustments=0.0,
            adjusted_gross_income=round(gross_income, 2),
            deductions=round(self.standard_deduction, 2),
            taxable_income=round(taxable_income, 2),
            tax_before_credits=round(base_tax, 2),
            credits=round(credits.total_credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            tax_withheld=round(state_withheld, 2),
            estimated_payments=round(estimated_payments, 2),
            deduction_method="standard",
            bracket_breakdown=bracket_breakdown,
        )


# ---------------------------------------------------------------------------
# Pennsylvania (PA-40) - flat 3.07% on taxable income
# ---------------------------------------------------------------------------
PA_FLAT_RATE = 0.0307


class PennsylvaniaTaxCalculator:
    """Calculate Pennsylvania state income tax (PA-40). Flat 3.07%."""

    def __init__(self, filing_status: FilingStatus = FilingStatus.SINGLE, tax_year: int = 2025):
        self.filing_status = filing_status
        self.tax_year = tax_year

    def calculate(
        self,
        income: TaxableIncome,
        deductions: Deductions,
        credits: TaxCredits,
        state_withheld: float,
        num_exemptions: int = 1,
        is_renter: bool = False,
        schedule_a_data: Optional[ScheduleAData] = None,
        schedule_e_summary: Optional[ScheduleESummary] = None,
        estimated_payments: float = 0.0,
        us_treasury_interest: float = 0.0,
        federal_agi: float = 0.0,
    ) -> TaxCalculation:
        gross_income = income.total_income - us_treasury_interest
        # PA has no standard deduction; taxable = gross (simplified)
        taxable_income = max(0, gross_income)
        base_tax = taxable_income * PA_FLAT_RATE
        tax_after_credits = max(0, base_tax - credits.total_credits)
        breakdown = [{"bracket": "All income", "rate": PA_FLAT_RATE, "income": taxable_income, "tax": base_tax}]
        return TaxCalculation(
            jurisdiction="Pennsylvania",
            tax_year=self.tax_year,
            gross_income=round(gross_income, 2),
            adjustments=0.0,
            adjusted_gross_income=round(gross_income, 2),
            deductions=0.0,
            taxable_income=round(taxable_income, 2),
            tax_before_credits=round(base_tax, 2),
            credits=round(credits.total_credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            tax_withheld=round(state_withheld, 2),
            estimated_payments=round(estimated_payments, 2),
            deduction_method="none",
            bracket_breakdown=breakdown,
        )


def calculate_state_tax(
    state_code: str,
    filing_status: FilingStatus,
    tax_year: int,
    income: TaxableIncome,
    deductions: Deductions,
    credits: TaxCredits,
    state_withheld: float,
    num_exemptions: int = 1,
    is_renter: bool = False,
    schedule_a_data: Optional[ScheduleAData] = None,
    schedule_e_summary: Optional[ScheduleESummary] = None,
    estimated_payments: float = 0.0,
    us_treasury_interest: float = 0.0,
    federal_agi: float = 0.0,
) -> Optional[TaxCalculation]:
    """
    Calculate state income tax for the given state of residence.

    Returns TaxCalculation for CA, NY, and other implemented states;
    Returns None for no-income-tax states (e.g. TX, FL) or unimplemented states.
    """
    state_code = (state_code or "").strip().upper()
    if len(state_code) != 2:
        return None
    if state_code in STATES_NO_INCOME_TAX:
        return None

    if state_code == "CA":
        from .california_tax import CaliforniaTaxCalculator
        calc = CaliforniaTaxCalculator(filing_status=filing_status, tax_year=tax_year)
        return calc.calculate(
            income=income,
            deductions=deductions,
            credits=credits,
            state_withheld=state_withheld,
            num_exemptions=num_exemptions,
            is_renter=is_renter,
            schedule_a_data=schedule_a_data,
            schedule_e_summary=schedule_e_summary,
            estimated_payments=estimated_payments,
            us_treasury_interest=us_treasury_interest,
            federal_agi=federal_agi,
        )

    if state_code == "NY":
        ny_calc = NewYorkTaxCalculator(filing_status=filing_status, tax_year=tax_year)
        return ny_calc.calculate(
            income=income,
            deductions=deductions,
            credits=credits,
            state_withheld=state_withheld,
            num_exemptions=num_exemptions,
            is_renter=is_renter,
            schedule_a_data=schedule_a_data,
            schedule_e_summary=schedule_e_summary,
            estimated_payments=estimated_payments,
            us_treasury_interest=us_treasury_interest,
            federal_agi=federal_agi,
        )

    if state_code == "NJ":
        nj_calc = NewJerseyTaxCalculator(filing_status=filing_status, tax_year=tax_year)
        return nj_calc.calculate(
            income=income,
            deductions=deductions,
            credits=credits,
            state_withheld=state_withheld,
            num_exemptions=num_exemptions,
            is_renter=is_renter,
            schedule_a_data=schedule_a_data,
            schedule_e_summary=schedule_e_summary,
            estimated_payments=estimated_payments,
            us_treasury_interest=us_treasury_interest,
            federal_agi=federal_agi,
        )

    if state_code == "PA":
        pa_calc = PennsylvaniaTaxCalculator(filing_status=filing_status, tax_year=tax_year)
        return pa_calc.calculate(
            income=income,
            deductions=deductions,
            credits=credits,
            state_withheld=state_withheld,
            num_exemptions=num_exemptions,
            is_renter=is_renter,
            schedule_a_data=schedule_a_data,
            schedule_e_summary=schedule_e_summary,
            estimated_payments=estimated_payments,
            us_treasury_interest=us_treasury_interest,
            federal_agi=federal_agi,
        )

    return None


def get_state_calculation_support() -> dict:
    """Return { state_code: display_name } for states with implemented tax calculation."""
    return {
        "CA": "California (Form 540)",
        "NY": "New York (IT-201)",
        "NJ": "New Jersey (NJ-1040)",
        "PA": "Pennsylvania (PA-40)",
    }
