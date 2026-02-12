"""California state tax calculation (Form 540) for tax years 2024 and 2025."""

from typing import Tuple, Optional
from .models import (
    FilingStatus, TaxableIncome, Deductions, TaxCredits, TaxCalculation,
    ScheduleAData, ScheduleAResult, ScheduleESummary,
)
from .schedule_a import ScheduleACalculator


# ---------------------------------------------------------------------------
# 2025 California Tax Brackets (estimated)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 2024 California Tax Brackets (actual)
# ---------------------------------------------------------------------------
CA_TAX_BRACKETS_2024 = {
    FilingStatus.SINGLE: [
        (10_412, 0.01),
        (24_684, 0.02),
        (38_959, 0.04),
        (54_081, 0.06),
        (68_350, 0.08),
        (349_137, 0.093),
        (418_961, 0.103),
        (698_271, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_JOINTLY: [
        (20_824, 0.01),
        (49_368, 0.02),
        (77_918, 0.04),
        (108_162, 0.06),
        (136_700, 0.08),
        (698_274, 0.093),
        (837_922, 0.103),
        (1_396_542, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.MARRIED_FILING_SEPARATELY: [
        (10_412, 0.01),
        (24_684, 0.02),
        (38_959, 0.04),
        (54_081, 0.06),
        (68_350, 0.08),
        (349_137, 0.093),
        (418_961, 0.103),
        (698_271, 0.113),
        (float('inf'), 0.123),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (20_839, 0.01),
        (49_371, 0.02),
        (63_644, 0.04),
        (78_765, 0.06),
        (93_037, 0.08),
        (474_824, 0.093),
        (569_790, 0.103),
        (949_649, 0.113),
        (float('inf'), 0.123),
    ],
}

# ---------------------------------------------------------------------------
# Standard Deductions
# ---------------------------------------------------------------------------
CA_STANDARD_DEDUCTION = {
    2024: {
        FilingStatus.SINGLE: 5_363,
        FilingStatus.MARRIED_FILING_JOINTLY: 10_726,
        FilingStatus.MARRIED_FILING_SEPARATELY: 5_363,
        FilingStatus.HEAD_OF_HOUSEHOLD: 10_726,
    },
    2025: {
        FilingStatus.SINGLE: 5_540,
        FilingStatus.MARRIED_FILING_JOINTLY: 11_080,
        FilingStatus.MARRIED_FILING_SEPARATELY: 5_540,
        FilingStatus.HEAD_OF_HOUSEHOLD: 11_080,
    },
}

# Exemption credit per exemption
CA_EXEMPTION_CREDIT = {2024: 140, 2025: 144}

# Exemption credit phaseout thresholds (federal AGI)
# Credit reduces by $6 per $2,500 (or fraction) of AGI over threshold
CA_EXEMPTION_PHASEOUT = {
    2024: {
        FilingStatus.SINGLE: 244_860,
        FilingStatus.MARRIED_FILING_JOINTLY: 489_719,
        FilingStatus.MARRIED_FILING_SEPARATELY: 244_860,
        FilingStatus.HEAD_OF_HOUSEHOLD: 367_290,
    },
    2025: {
        FilingStatus.SINGLE: 252_813,
        FilingStatus.MARRIED_FILING_JOINTLY: 505_626,
        FilingStatus.MARRIED_FILING_SEPARATELY: 252_813,
        FilingStatus.HEAD_OF_HOUSEHOLD: 379_220,
    },
}
CA_EXEMPTION_PHASEOUT_PER_2500 = 6  # $6 reduction per $2,500 excess

# Mental Health Services Tax (Prop 63)
CA_MENTAL_HEALTH_THRESHOLD = 1_000_000
CA_MENTAL_HEALTH_RATE = 0.01

# SDI
CA_SDI_RATE = {2024: 0.009, 2025: 0.009}
CA_SDI_WAGE_BASE = {2024: 153_164, 2025: 153_164}

# ---------------------------------------------------------------------------
# CA Renter's Credit
# ---------------------------------------------------------------------------
CA_RENTERS_CREDIT = {
    2024: {
        FilingStatus.SINGLE: 60,
        FilingStatus.MARRIED_FILING_JOINTLY: 120,
        FilingStatus.MARRIED_FILING_SEPARATELY: 60,
        FilingStatus.HEAD_OF_HOUSEHOLD: 120,
    },
    2025: {
        FilingStatus.SINGLE: 60,
        FilingStatus.MARRIED_FILING_JOINTLY: 120,
        FilingStatus.MARRIED_FILING_SEPARATELY: 60,
        FilingStatus.HEAD_OF_HOUSEHOLD: 120,
    },
}
# AGI limits for Renter's Credit eligibility
CA_RENTERS_CREDIT_AGI_LIMIT = {
    2024: {
        FilingStatus.SINGLE: 50_746,
        FilingStatus.MARRIED_FILING_JOINTLY: 101_492,
        FilingStatus.MARRIED_FILING_SEPARATELY: 50_746,
        FilingStatus.HEAD_OF_HOUSEHOLD: 101_492,
    },
    2025: {
        FilingStatus.SINGLE: 52_000,
        FilingStatus.MARRIED_FILING_JOINTLY: 104_000,
        FilingStatus.MARRIED_FILING_SEPARATELY: 52_000,
        FilingStatus.HEAD_OF_HOUSEHOLD: 104_000,
    },
}


def _get_ca_brackets(tax_year: int, filing_status: FilingStatus):
    if tax_year == 2024:
        return CA_TAX_BRACKETS_2024[filing_status]
    return CA_TAX_BRACKETS_2025[filing_status]


class CaliforniaTaxCalculator:
    """Calculate California state income tax (Form 540)."""

    def __init__(
        self,
        filing_status: FilingStatus = FilingStatus.SINGLE,
        tax_year: int = 2025,
    ):
        self.filing_status = filing_status
        self.tax_year = tax_year
        self.brackets = _get_ca_brackets(tax_year, filing_status)

        std = CA_STANDARD_DEDUCTION.get(tax_year, CA_STANDARD_DEDUCTION[2025])
        self.standard_deduction = std[filing_status]

    def get_standard_deduction(self) -> float:
        return self.standard_deduction

    def calculate_progressive_tax(self, taxable_income: float) -> Tuple[float, list]:
        """Calculate CA tax using progressive brackets."""
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

    def calculate_mental_health_tax(self, taxable_income: float) -> float:
        if taxable_income > CA_MENTAL_HEALTH_THRESHOLD:
            return (taxable_income - CA_MENTAL_HEALTH_THRESHOLD) * CA_MENTAL_HEALTH_RATE
        return 0.0

    def calculate_exemption_credit(
        self, num_exemptions: int = 1, federal_agi: float = 0.0,
    ) -> float:
        """Calculate CA exemption credit with phaseout for high incomes.

        The credit reduces by $6 for each $2,500 (or fraction thereof)
        of federal AGI exceeding the phaseout threshold.
        """
        credit_per = CA_EXEMPTION_CREDIT.get(self.tax_year, 144)
        base_credit = credit_per * num_exemptions

        if federal_agi <= 0 or base_credit <= 0:
            return base_credit

        thresholds = CA_EXEMPTION_PHASEOUT.get(
            self.tax_year, CA_EXEMPTION_PHASEOUT[2025]
        )
        threshold = thresholds.get(self.filing_status, thresholds[FilingStatus.SINGLE])

        if federal_agi <= threshold:
            return base_credit

        import math
        excess = federal_agi - threshold
        increments = math.ceil(excess / 2_500)
        reduction = increments * CA_EXEMPTION_PHASEOUT_PER_2500
        return max(0, base_credit - reduction)

    def calculate_renters_credit(
        self, ca_agi: float, is_renter: bool
    ) -> float:
        """
        Calculate CA Renter's Credit.

        Available to CA residents who rented their primary residence for
        at least half the year and whose AGI is below the threshold.
        """
        if not is_renter:
            return 0.0

        limits = CA_RENTERS_CREDIT_AGI_LIMIT.get(
            self.tax_year, CA_RENTERS_CREDIT_AGI_LIMIT[2025]
        )
        agi_limit = limits[self.filing_status]

        if ca_agi > agi_limit:
            return 0.0

        amounts = CA_RENTERS_CREDIT.get(self.tax_year, CA_RENTERS_CREDIT[2025])
        return amounts[self.filing_status]

    def apply_ca_adjustments(self, income: TaxableIncome) -> float:
        """
        Apply California-specific income adjustments.

        CA differences from federal:
        - CA taxes Social Security income (federal may exclude some)
        - CA does not tax certain bond interest (e.g., CA muni bonds)
        - CA adds back certain federal deductions

        For this implementation we apply the main adjustment:
        SE tax deduction (CA conforms to federal).

        Returns the CA adjustment amount.
        """
        adjustments = 0.0
        if income.self_employment_income > 0:
            se_net = income.self_employment_income * 0.9235
            se_tax = se_net * 0.153
            adjustments = se_tax / 2  # Half of SE tax is deductible
        return adjustments

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
        """
        Calculate complete California tax liability (Form 540).

        Args:
            income: Taxable income breakdown.
            deductions: Deduction information.
            credits: Tax credits (CA-specific).
            state_withheld: Total state tax withheld.
            num_exemptions: Number of CA exemptions.
            is_renter: Whether taxpayer is a CA renter (for Renter's Credit).
            schedule_a_data: Itemized deduction inputs.
            schedule_e_summary: Pre-computed Schedule E summary.
            estimated_payments: Total CA estimated tax payments.

        Returns:
            Complete California TaxCalculation result.
        """
        # --- CA Gross Income ---
        # Subtract US Treasury interest (exempt from CA tax)
        gross_income = income.total_income - us_treasury_interest

        # --- CA Adjustments ---
        adjustments = self.apply_ca_adjustments(income)

        # --- CA AGI ---
        ca_agi = gross_income - adjustments

        # --- CA Deductions ---
        ca_std = self.get_standard_deduction()
        schedule_a_result = None

        if schedule_a_data:
            schedule_a_result = ScheduleACalculator.calculate_ca_itemized(
                data=schedule_a_data,
                agi=ca_agi,
                ca_standard_deduction=ca_std,
                filing_status=self.filing_status,
                tax_year=self.tax_year,
            )
            deduction_amount = schedule_a_result.deduction_amount
            deduction_method = "itemized" if schedule_a_result.use_itemized else "standard"
        elif not deductions.use_standard:
            # Legacy path: CA itemized without SALT cap
            ca_itemized = (
                deductions.state_local_taxes +
                deductions.mortgage_interest +
                deductions.charitable_contributions +
                deductions.medical_expenses
            )
            deduction_amount = max(ca_itemized, ca_std)
            deduction_method = "itemized" if ca_itemized > ca_std else "standard"
        else:
            deduction_amount = ca_std
            deduction_method = "standard"

        # --- CA Taxable Income ---
        taxable_income = max(0, ca_agi - deduction_amount)

        # --- CA Tax ---
        base_tax, bracket_breakdown = self.calculate_progressive_tax(taxable_income)
        mental_health_tax = self.calculate_mental_health_tax(taxable_income)
        tax_before_credits = base_tax + mental_health_tax

        # --- CA Credits ---
        exemption_credit = self.calculate_exemption_credit(num_exemptions, federal_agi)
        renters_credit = self.calculate_renters_credit(ca_agi, is_renter)
        total_credits = credits.total_credits + exemption_credit + renters_credit

        # Tax after credits
        tax_after_credits = max(0, tax_before_credits - total_credits)

        return TaxCalculation(
            jurisdiction="California",
            tax_year=self.tax_year,
            gross_income=round(gross_income, 2),
            adjustments=round(adjustments, 2),
            adjusted_gross_income=round(ca_agi, 2),
            deductions=round(deduction_amount, 2),
            taxable_income=round(taxable_income, 2),
            tax_before_credits=round(tax_before_credits, 2),
            credits=round(total_credits, 2),
            tax_after_credits=round(tax_after_credits, 2),
            tax_withheld=round(state_withheld, 2),
            estimated_payments=round(estimated_payments, 2),
            deduction_method=deduction_method,
            bracket_breakdown=bracket_breakdown,
            schedule_e_summary=schedule_e_summary,
            schedule_a_result=schedule_a_result,
            ca_exemption_credit=round(exemption_credit, 2),
            ca_mental_health_tax=round(mental_health_tax, 2),
            ca_renters_credit=round(renters_credit, 2),
        )

    def calculate_effective_rate(self, tax_calculation: TaxCalculation) -> float:
        if tax_calculation.gross_income <= 0:
            return 0.0
        return tax_calculation.tax_after_credits / tax_calculation.gross_income

    def calculate_marginal_rate(self, taxable_income: float) -> float:
        for upper_limit, rate in self.brackets:
            if taxable_income <= upper_limit:
                return rate
        return self.brackets[-1][1]


def calculate_california_tax(
    filing_status: FilingStatus,
    income: TaxableIncome,
    deductions: Deductions,
    credits: TaxCredits,
    state_withheld: float,
    num_exemptions: int = 1,
    tax_year: int = 2025,
    is_renter: bool = False,
    schedule_a_data: Optional[ScheduleAData] = None,
    schedule_e_summary: Optional[ScheduleESummary] = None,
    estimated_payments: float = 0.0,
    us_treasury_interest: float = 0.0,
    federal_agi: float = 0.0,
) -> TaxCalculation:
    """Convenience function to calculate California tax."""
    calculator = CaliforniaTaxCalculator(filing_status, tax_year)
    return calculator.calculate(
        income, deductions, credits, state_withheld, num_exemptions,
        is_renter, schedule_a_data, schedule_e_summary, estimated_payments,
        us_treasury_interest, federal_agi,
    )


def calculate_sdi(wages: float, tax_year: int = 2025) -> float:
    """Calculate California State Disability Insurance."""
    rate = CA_SDI_RATE.get(tax_year, 0.009)
    base = CA_SDI_WAGE_BASE.get(tax_year, 153_164)
    return min(wages, base) * rate
