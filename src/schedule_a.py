"""Schedule A (Itemized Deductions) Calculator.

Handles the computation of itemized deductions including:
- Medical expenses (subject to 7.5% AGI floor)
- State and Local Taxes (SALT) with $10,000 federal cap
- CA Vehicle License Fee (VLF) as personal property tax
- Mortgage interest
- Charitable contributions
- Standard vs. Itemized comparison
"""

from .models import (
    FilingStatus, ScheduleAData, ScheduleAResult,
)

# Federal SALT cap
FEDERAL_SALT_CAP = 10_000
FEDERAL_SALT_CAP_MFS = 5_000  # Married Filing Separately

# Medical expense AGI floor
MEDICAL_AGI_FLOOR_RATE = 0.075  # 7.5% of AGI

# Mortgage acquisition debt limits (TCJA: post-Dec 15, 2017 mortgages)
FEDERAL_MORTGAGE_DEBT_LIMIT = 750_000
FEDERAL_MORTGAGE_DEBT_LIMIT_MFS = 375_000
CA_MORTGAGE_DEBT_LIMIT = 1_000_000  # CA did not conform to TCJA reduction
CA_MORTGAGE_DEBT_LIMIT_MFS = 500_000

# ---------------------------------------------------------------------------
# CA Itemized Deduction Limitation (high-income phaseout)
# ---------------------------------------------------------------------------
CA_ITEMIZED_LIMITATION_THRESHOLD = {
    2024: {
        FilingStatus.SINGLE: 226_382,
        FilingStatus.MARRIED_FILING_JOINTLY: 452_761,
        FilingStatus.MARRIED_FILING_SEPARATELY: 226_382,
        FilingStatus.HEAD_OF_HOUSEHOLD: 339_571,
    },
    2025: {
        FilingStatus.SINGLE: 233_774,
        FilingStatus.MARRIED_FILING_JOINTLY: 467_547,
        FilingStatus.MARRIED_FILING_SEPARATELY: 233_774,
        FilingStatus.HEAD_OF_HOUSEHOLD: 350_660,
    },
}
CA_ITEMIZED_LIMITATION_RATE = 0.06
CA_ITEMIZED_LIMITATION_MAX_RATE = 0.80


class ScheduleACalculator:
    """Calculate Schedule A (Itemized Deductions)."""

    def __init__(
        self,
        filing_status: FilingStatus = FilingStatus.SINGLE,
        standard_deduction: float = 0.0,
    ):
        self.filing_status = filing_status
        self.standard_deduction = standard_deduction

    def calculate(
        self,
        data: ScheduleAData,
        agi: float,
    ) -> ScheduleAResult:
        """
        Compute Schedule A itemized deductions and compare to standard.

        Args:
            data: ScheduleAData with all itemized deduction inputs.
            agi: Adjusted Gross Income (needed for medical expense floor).

        Returns:
            ScheduleAResult with breakdown and recommendation.
        """
        # --- Medical Expenses (Line 1-4) ---
        medical_floor = agi * MEDICAL_AGI_FLOOR_RATE
        medical_deduction = max(0, data.medical_expenses - medical_floor)

        # --- Taxes Paid / SALT (Line 5-7) ---
        # Include: state income tax, real estate taxes, personal property taxes, VLF
        vlf_total = data.total_vehicle_license_fees
        salt_uncapped = (
            data.state_income_tax_paid +
            data.real_estate_taxes +
            data.personal_property_taxes +
            vlf_total
        )

        # Apply federal SALT cap
        salt_cap = (
            FEDERAL_SALT_CAP_MFS
            if self.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY
            else FEDERAL_SALT_CAP
        )
        salt_deduction = min(salt_uncapped, salt_cap)

        # --- Interest (Line 8-10) ---
        home_mortgage = data.mortgage_interest + data.mortgage_points
        # Apply federal mortgage debt limit proration
        if data.mortgage_balance > 0:
            limit = (
                FEDERAL_MORTGAGE_DEBT_LIMIT_MFS
                if self.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY
                else FEDERAL_MORTGAGE_DEBT_LIMIT
            )
            if data.mortgage_balance > limit:
                home_mortgage *= limit / data.mortgage_balance
        mortgage_interest_deduction = home_mortgage + data.investment_interest

        # --- Charitable Contributions (Line 11-14) ---
        charitable_deduction = data.cash_contributions + data.noncash_contributions

        # --- Other Deductions (Line 16) ---
        other_deductions = data.casualty_losses + data.other_deductions

        # --- Total Itemized ---
        total_itemized = (
            medical_deduction +
            salt_deduction +
            mortgage_interest_deduction +
            charitable_deduction +
            other_deductions
        )

        # --- Standard vs. Itemized comparison ---
        use_itemized = total_itemized > self.standard_deduction
        deduction_amount = total_itemized if use_itemized else self.standard_deduction

        return ScheduleAResult(
            medical_deduction=round(medical_deduction, 2),
            salt_deduction=round(salt_deduction, 2),
            salt_uncapped=round(salt_uncapped, 2),
            mortgage_interest_deduction=round(mortgage_interest_deduction, 2),
            charitable_deduction=round(charitable_deduction, 2),
            other_deductions=round(other_deductions, 2),
            total_itemized=round(total_itemized, 2),
            standard_deduction=self.standard_deduction,
            use_itemized=use_itemized,
            deduction_amount=round(deduction_amount, 2),
        )

    @staticmethod
    def calculate_ca_itemized(
        data: ScheduleAData,
        agi: float,
        ca_standard_deduction: float,
        filing_status: FilingStatus = FilingStatus.SINGLE,
        tax_year: int = 2025,
    ) -> ScheduleAResult:
        """
        Compute California-specific itemized deductions.

        Key CA differences from federal:
        - No SALT cap (CA does not limit state/local tax deduction)
        - CA does not allow state income tax as an itemized deduction
          (you can't deduct CA tax on your CA return)
        - VLF is deductible as personal property tax (no cap)
        - Medical expense threshold same as federal (7.5%)
        - High-income limitation: reduce by min(6% * (AGI - threshold), 80% * itemized)

        Args:
            data: ScheduleAData with all inputs.
            agi: California AGI.
            ca_standard_deduction: CA standard deduction for comparison.
            filing_status: Filing status for limitation threshold.
            tax_year: Tax year for limitation threshold.

        Returns:
            ScheduleAResult for California.
        """
        # Medical
        medical_floor = agi * MEDICAL_AGI_FLOOR_RATE
        medical_deduction = max(0, data.medical_expenses - medical_floor)

        # Taxes paid - CA does NOT allow deduction of state income taxes
        # on the CA return, but does allow real estate taxes and VLF
        vlf_total = data.total_vehicle_license_fees
        salt_uncapped = (
            data.real_estate_taxes +
            data.personal_property_taxes +
            vlf_total
            # Note: state_income_tax_paid is excluded for CA
        )
        # CA has no SALT cap
        salt_deduction = salt_uncapped

        # Interest - CA uses $1M debt limit (did not conform to TCJA $750K)
        home_mortgage = data.mortgage_interest + data.mortgage_points
        if data.mortgage_balance > 0:
            ca_limit = (
                CA_MORTGAGE_DEBT_LIMIT_MFS
                if filing_status == FilingStatus.MARRIED_FILING_SEPARATELY
                else CA_MORTGAGE_DEBT_LIMIT
            )
            if data.mortgage_balance > ca_limit:
                home_mortgage *= ca_limit / data.mortgage_balance
        mortgage_interest_deduction = home_mortgage + data.investment_interest

        # Charitable - same as federal
        charitable_deduction = data.cash_contributions + data.noncash_contributions

        # Other
        other_deductions = data.casualty_losses + data.other_deductions

        total_itemized = (
            medical_deduction +
            salt_deduction +
            mortgage_interest_deduction +
            charitable_deduction +
            other_deductions
        )

        # CA itemized deduction limitation for high-income taxpayers
        ca_limitation = 0.0
        thresholds = CA_ITEMIZED_LIMITATION_THRESHOLD.get(
            tax_year, CA_ITEMIZED_LIMITATION_THRESHOLD[2025]
        )
        threshold = thresholds[filing_status]
        if agi > threshold and total_itemized > 0:
            ca_limitation = min(
                CA_ITEMIZED_LIMITATION_RATE * (agi - threshold),
                CA_ITEMIZED_LIMITATION_MAX_RATE * total_itemized,
            )
            total_itemized -= ca_limitation

        use_itemized = total_itemized > ca_standard_deduction
        deduction_amount = total_itemized if use_itemized else ca_standard_deduction

        return ScheduleAResult(
            medical_deduction=round(medical_deduction, 2),
            salt_deduction=round(salt_deduction, 2),
            salt_uncapped=round(salt_uncapped, 2),
            mortgage_interest_deduction=round(mortgage_interest_deduction, 2),
            charitable_deduction=round(charitable_deduction, 2),
            other_deductions=round(other_deductions, 2),
            total_itemized=round(total_itemized, 2),
            standard_deduction=ca_standard_deduction,
            use_itemized=use_itemized,
            deduction_amount=round(deduction_amount, 2),
            ca_itemized_limitation=round(ca_limitation, 2),
        )
