"""Schedule E (Supplemental Income and Loss) - Rental Real Estate.

Handles rental property income, expenses, and depreciation calculations
for both Federal and California returns.
"""

from datetime import date
from typing import List

from .models import RentalProperty, ScheduleEResult, ScheduleESummary


# Residential rental property depreciation: 27.5 years straight-line
RESIDENTIAL_DEPRECIATION_YEARS = 27.5


class DepreciationCalculator:
    """Calculate depreciation for rental properties using straight-line method."""

    @staticmethod
    def calculate_annual_depreciation(
        depreciable_basis: float,
        useful_life_years: float = RESIDENTIAL_DEPRECIATION_YEARS,
        months_in_service: int = 12,
    ) -> float:
        """
        Calculate annual depreciation using straight-line method.

        For residential rental property, the IRS requires 27.5-year
        straight-line depreciation. In the first/last year, depreciation
        is prorated by the number of months the property was in service
        (mid-month convention).

        Args:
            depreciable_basis: Cost basis minus land value.
            useful_life_years: Recovery period (27.5 for residential rental).
            months_in_service: Months the property was available for rent
                               in the tax year (1-12).

        Returns:
            Annual depreciation amount.
        """
        if depreciable_basis <= 0 or useful_life_years <= 0:
            return 0.0

        full_year_depreciation = depreciable_basis / useful_life_years
        # Pro-rate for partial year (mid-month convention simplified)
        return full_year_depreciation * (months_in_service / 12.0)

    @staticmethod
    def calculate_months_in_service(
        purchase_date: date,
        tax_year: int,
    ) -> int:
        """
        Determine months in service for a given tax year.

        Uses mid-month convention: property placed in service in the middle
        of the purchase month.

        Args:
            purchase_date: Date the property was placed in service.
            tax_year: The tax year being calculated.

        Returns:
            Number of months in service (0-12).
        """
        if purchase_date.year > tax_year:
            return 0  # Not yet in service
        if purchase_date.year < tax_year:
            return 12  # Full year

        # First year: mid-month convention
        # Property placed in service mid-month, so count from that month
        # Month placed in service counts as half month (simplified: full month)
        months = 12 - purchase_date.month + 1
        return max(0, min(12, months))


class ScheduleECalculator:
    """Calculate Schedule E (Rental Income and Loss)."""

    def __init__(self, tax_year: int = 2025):
        self.tax_year = tax_year
        self.depreciation_calc = DepreciationCalculator()

    def calculate_property(self, prop: RentalProperty) -> ScheduleEResult:
        """
        Calculate Schedule E for a single rental property.

        Args:
            prop: RentalProperty with income and expense data.

        Returns:
            ScheduleEResult with computed values.
        """
        gross_income = prop.rental_income
        total_expenses = prop.total_expenses

        # Calculate depreciation
        depreciation = 0.0
        if prop.depreciable_basis > 0:
            if prop.purchase_date:
                months = self.depreciation_calc.calculate_months_in_service(
                    prop.purchase_date, self.tax_year
                )
            else:
                months = 12  # Assume full year if no date provided

            depreciation = self.depreciation_calc.calculate_annual_depreciation(
                depreciable_basis=prop.depreciable_basis,
                months_in_service=months,
            )

        # If property has personal use, prorate expenses
        total_days = prop.days_rented + prop.personal_use_days
        if total_days > 0 and prop.personal_use_days > 0:
            rental_ratio = prop.days_rented / total_days
            total_expenses *= rental_ratio
            depreciation *= rental_ratio

        net_income = gross_income - total_expenses - depreciation

        return ScheduleEResult(
            address=prop.address,
            gross_income=gross_income,
            total_expenses=total_expenses,
            depreciation=round(depreciation, 2),
            net_income=round(net_income, 2),
        )

    def calculate_all(self, properties: List[RentalProperty]) -> ScheduleESummary:
        """
        Calculate Schedule E for all rental properties.

        Args:
            properties: List of RentalProperty objects.

        Returns:
            ScheduleESummary with per-property and total results.
        """
        results = [self.calculate_property(p) for p in properties]
        return ScheduleESummary(properties=results)
