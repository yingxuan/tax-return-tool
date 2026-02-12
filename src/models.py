"""Data models for tax return information."""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import date


class FilingStatus(Enum):
    """Tax filing status options."""
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


# ---------------------------------------------------------------------------
# Dependents
# ---------------------------------------------------------------------------

@dataclass
class Dependent:
    """A dependent claimed on the tax return."""
    name: str
    age: int
    relationship: str  # e.g. "son", "daughter", "parent"
    ssn: Optional[str] = None
    qualifies_for_child_tax_credit: bool = False  # under 17 at end of tax year

    def __post_init__(self):
        if self.age < 17:
            self.qualifies_for_child_tax_credit = True


# ---------------------------------------------------------------------------
# Form data models
# ---------------------------------------------------------------------------

@dataclass
class W2Data:
    """W-2 form data for wage and salary information."""
    employer_name: str
    employer_ein: Optional[str] = None
    wages: float = 0.0  # Box 1: Wages, tips, other compensation
    federal_withheld: float = 0.0  # Box 2: Federal income tax withheld
    social_security_wages: float = 0.0  # Box 3
    social_security_tax: float = 0.0  # Box 4
    medicare_wages: float = 0.0  # Box 5
    medicare_tax: float = 0.0  # Box 6
    dependent_care_benefits: float = 0.0  # Box 10: Dependent care benefits (FSA)
    state: Optional[str] = None  # Box 15
    state_wages: float = 0.0  # Box 16
    state_withheld: float = 0.0  # Box 17


@dataclass
class Form1099Int:
    """1099-INT form data for interest income."""
    payer_name: str
    interest_income: float = 0.0  # Box 1
    us_treasury_interest: float = 0.0  # Box 3: Interest on U.S. Treasury obligations
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099Div:
    """1099-DIV form data for dividend income."""
    payer_name: str
    ordinary_dividends: float = 0.0  # Box 1a
    qualified_dividends: float = 0.0  # Box 1b
    capital_gain_distributions: float = 0.0  # Box 2a
    us_treasury_interest: float = 0.0  # Exempt-interest dividends from US Treasury
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099Misc:
    """1099-MISC form data for miscellaneous income."""
    payer_name: str
    rents: float = 0.0  # Box 1
    other_income: float = 0.0  # Box 3
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099Nec:
    """1099-NEC form data for non-employee compensation."""
    payer_name: str
    nonemployee_compensation: float = 0.0  # Box 1
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099R:
    """1099-R form data for retirement distributions."""
    payer_name: str
    gross_distribution: float = 0.0  # Box 1
    taxable_amount: float = 0.0  # Box 2a
    taxable_amount_not_determined: bool = False  # Box 2b checkbox
    federal_withheld: float = 0.0  # Box 4
    distribution_code: str = ""  # Box 7
    state_withheld: float = 0.0  # Box 12


@dataclass
class Form1099B:
    """1099-B form data for broker transactions."""
    broker_name: str
    description: str = ""
    date_acquired: Optional[str] = None
    date_sold: Optional[str] = None
    proceeds: float = 0.0
    cost_basis: float = 0.0
    gain_loss: float = 0.0
    is_short_term: bool = False


@dataclass
class Form1099G:
    """1099-G form data for government payments."""
    payer_name: str
    state_tax_refund: float = 0.0  # Box 2
    unemployment_compensation: float = 0.0  # Box 1
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1098:
    """1098 form data for mortgage interest."""
    lender_name: str
    mortgage_interest: float = 0.0  # Box 1
    points_paid: float = 0.0  # Box 6
    property_taxes: float = 0.0  # Box 10 (if reported)
    is_rental: bool = False  # True if this mortgage is for a rental property


@dataclass
class Form1098T:
    """1098-T form data for tuition payments."""
    institution_name: str
    amounts_billed: float = 0.0  # Box 1
    scholarships_grants: float = 0.0  # Box 5


# ---------------------------------------------------------------------------
# Rental Property / Schedule E
# ---------------------------------------------------------------------------

@dataclass
class RentalProperty:
    """A single rental property for Schedule E."""
    address: str
    property_type: str = "Single Family"  # Single Family, Multi-Family, etc.
    purchase_price: float = 0.0
    purchase_date: Optional[date] = None
    land_value: float = 0.0  # Land is not depreciable
    days_rented: int = 365
    personal_use_days: int = 0

    # Income
    rental_income: float = 0.0  # Gross rents received

    # Expenses
    advertising: float = 0.0
    auto_and_travel: float = 0.0
    cleaning_and_maintenance: float = 0.0
    commissions: float = 0.0
    insurance: float = 0.0
    legal_and_professional: float = 0.0
    management_fees: float = 0.0
    mortgage_interest: float = 0.0
    property_tax: float = 0.0
    repairs: float = 0.0
    supplies: float = 0.0
    utilities: float = 0.0
    other_expenses: float = 0.0

    @property
    def depreciable_basis(self) -> float:
        """Calculate the depreciable basis (purchase price minus land value)."""
        return max(0, self.purchase_price - self.land_value)

    @property
    def total_expenses(self) -> float:
        """Sum of all operating expenses (excluding depreciation)."""
        return (
            self.advertising + self.auto_and_travel +
            self.cleaning_and_maintenance + self.commissions +
            self.insurance + self.legal_and_professional +
            self.management_fees + self.mortgage_interest +
            self.property_tax + self.repairs + self.supplies +
            self.utilities + self.other_expenses
        )


@dataclass
class ScheduleEResult:
    """Result of Schedule E (Rental) calculation for a single property."""
    address: str
    gross_income: float = 0.0
    total_expenses: float = 0.0
    depreciation: float = 0.0
    net_income: float = 0.0  # Can be negative (rental loss)


@dataclass
class ScheduleESummary:
    """Summary of all Schedule E rental activities."""
    properties: List[ScheduleEResult] = field(default_factory=list)

    @property
    def total_rental_income(self) -> float:
        return sum(p.gross_income for p in self.properties)

    @property
    def total_rental_expenses(self) -> float:
        return sum(p.total_expenses + p.depreciation for p in self.properties)

    @property
    def total_net_rental_income(self) -> float:
        return sum(p.net_income for p in self.properties)


# ---------------------------------------------------------------------------
# Schedule A (Itemized Deductions)
# ---------------------------------------------------------------------------

@dataclass
class CAVehicleRegistration:
    """California vehicle registration fee breakdown.
    Only the Vehicle License Fee (VLF) portion is deductible as a personal
    property tax on Schedule A."""
    total_registration_fee: float = 0.0
    vehicle_license_fee: float = 0.0  # The deductible portion (VLF)
    weight_fee: float = 0.0
    other_fees: float = 0.0


@dataclass
class ScheduleAData:
    """Schedule A (Itemized Deductions) input data."""
    # Medical and dental expenses
    medical_expenses: float = 0.0  # Subject to 7.5% AGI floor

    # Taxes paid
    state_income_tax_paid: float = 0.0
    real_estate_taxes: float = 0.0  # Property tax on primary residence
    personal_property_taxes: float = 0.0  # Includes VLF
    vehicle_registrations: List[CAVehicleRegistration] = field(default_factory=list)

    # Interest
    mortgage_interest: float = 0.0  # From Form 1098
    mortgage_points: float = 0.0
    investment_interest: float = 0.0
    mortgage_balance: float = 0.0  # Outstanding principal for debt limit proration

    # Charitable contributions
    cash_contributions: float = 0.0
    noncash_contributions: float = 0.0

    # Other
    casualty_losses: float = 0.0  # Federally declared disaster only
    other_deductions: float = 0.0

    @property
    def total_vehicle_license_fees(self) -> float:
        """Total deductible VLF from all vehicle registrations."""
        return sum(v.vehicle_license_fee for v in self.vehicle_registrations)


@dataclass
class ScheduleAResult:
    """Result of Schedule A computation."""
    medical_deduction: float = 0.0  # After 7.5% AGI floor
    salt_deduction: float = 0.0  # After $10,000 cap (federal)
    salt_uncapped: float = 0.0  # Before cap (for CA use)
    mortgage_interest_deduction: float = 0.0
    charitable_deduction: float = 0.0
    other_deductions: float = 0.0
    total_itemized: float = 0.0
    standard_deduction: float = 0.0
    use_itemized: bool = False  # True if itemized > standard
    deduction_amount: float = 0.0  # The higher of the two
    ca_itemized_limitation: float = 0.0  # CA high-income itemized deduction reduction


# ---------------------------------------------------------------------------
# Estimated Tax Payments
# ---------------------------------------------------------------------------

@dataclass
class EstimatedTaxPayment:
    """A quarterly estimated tax payment."""
    payment_date: Optional[date] = None
    amount: float = 0.0
    period: str = ""  # "Q1", "Q2", "Q3", "Q4"
    jurisdiction: str = "federal"  # "federal" or "california"


# ---------------------------------------------------------------------------
# Dependent Care (Form 2441)
# ---------------------------------------------------------------------------

@dataclass
class DependentCareFSA:
    """Dependent Care FSA / Form 2441 data."""
    provider_name: str = ""
    provider_address: str = ""
    provider_tin: str = ""
    amount_paid: float = 0.0
    fsa_contribution: float = 0.0  # Pre-tax W-2 Box 10
    # For 2024/2025: max $5,000 (MFJ) or $2,500 (MFS)
    # Credit is 20-35% of qualifying expenses up to $3,000 (1 child) or $6,000 (2+ children)


# ---------------------------------------------------------------------------
# Core tax structures
# ---------------------------------------------------------------------------

@dataclass
class TaxpayerInfo:
    """Basic taxpayer information."""
    name: str
    ssn: Optional[str] = None
    filing_status: FilingStatus = FilingStatus.SINGLE
    age: int = 30
    is_blind: bool = False
    dependents: List[Dependent] = field(default_factory=list)
    is_ca_resident: bool = True
    is_renter: bool = False  # For CA Renter's Credit

    @property
    def num_dependents(self) -> int:
        return len(self.dependents)

    @property
    def num_qualifying_children(self) -> int:
        """Children under 17 qualifying for Child Tax Credit."""
        return sum(1 for d in self.dependents if d.qualifies_for_child_tax_credit)

    @property
    def num_exemptions(self) -> int:
        """Total exemptions for CA (taxpayer + spouse if MFJ + dependents)."""
        base = 2 if self.filing_status == FilingStatus.MARRIED_FILING_JOINTLY else 1
        return base + self.num_dependents


@dataclass
class TaxableIncome:
    """Breakdown of taxable income sources."""
    wages: float = 0.0
    interest_income: float = 0.0
    dividend_income: float = 0.0
    qualified_dividends: float = 0.0
    capital_gains: float = 0.0
    short_term_capital_gains: float = 0.0
    long_term_capital_gains: float = 0.0
    other_income: float = 0.0
    self_employment_income: float = 0.0
    retirement_income: float = 0.0
    rental_income: float = 0.0  # Net rental income from Schedule E

    @property
    def total_income(self) -> float:
        """Calculate total gross income (Line 9 of Form 1040)."""
        return (
            self.wages +
            self.interest_income +
            self.dividend_income +
            self.capital_gains +
            self.other_income +
            self.self_employment_income +
            self.retirement_income +
            self.rental_income  # Can be negative (rental loss)
        )


@dataclass
class Deductions:
    """Tax deductions."""
    standard_deduction: float = 0.0
    itemized_deductions: float = 0.0
    use_standard: bool = True

    # Itemized deduction breakdown (legacy support)
    state_local_taxes: float = 0.0  # SALT, capped at $10,000
    mortgage_interest: float = 0.0
    charitable_contributions: float = 0.0
    medical_expenses: float = 0.0

    # Enhanced Schedule A result
    schedule_a_result: Optional[ScheduleAResult] = None

    @property
    def total_deductions(self) -> float:
        """Get the applicable deduction amount."""
        if self.schedule_a_result:
            return self.schedule_a_result.deduction_amount
        if self.use_standard:
            return self.standard_deduction
        return self.itemized_deductions


@dataclass
class TaxCredits:
    """Tax credits that reduce tax liability."""
    child_tax_credit: float = 0.0
    dependent_care_credit: float = 0.0
    earned_income_credit: float = 0.0
    education_credits: float = 0.0
    other_credits: float = 0.0

    @property
    def total_credits(self) -> float:
        """Calculate total credits."""
        return (
            self.child_tax_credit +
            self.dependent_care_credit +
            self.earned_income_credit +
            self.education_credits +
            self.other_credits
        )


@dataclass
class TaxCalculation:
    """Result of tax calculation for a single jurisdiction."""
    jurisdiction: str  # "Federal" or "California"
    tax_year: int = 2025
    gross_income: float = 0.0
    adjustments: float = 0.0
    adjusted_gross_income: float = 0.0
    deductions: float = 0.0
    taxable_income: float = 0.0
    tax_before_credits: float = 0.0
    credits: float = 0.0
    tax_after_credits: float = 0.0
    tax_withheld: float = 0.0
    estimated_payments: float = 0.0
    self_employment_tax: float = 0.0
    additional_medicare_tax: float = 0.0  # 0.9% on wages over threshold

    # NIIT and QD/LTCG breakdown
    niit: float = 0.0
    ordinary_income_tax: float = 0.0
    qualified_dividend_ltcg_tax: float = 0.0

    # Detailed breakdown for report
    deduction_method: str = "standard"  # "standard" or "itemized"
    bracket_breakdown: list = field(default_factory=list)
    schedule_e_summary: Optional[ScheduleESummary] = None
    schedule_a_result: Optional[ScheduleAResult] = None

    # Child Tax Credit detail
    child_tax_credit: float = 0.0
    num_qualifying_children: int = 0

    # CA-specific fields
    ca_exemption_credit: float = 0.0
    ca_mental_health_tax: float = 0.0
    ca_renters_credit: float = 0.0
    ca_sdi: float = 0.0

    @property
    def total_payments(self) -> float:
        """Total of withholding + estimated payments."""
        return self.tax_withheld + self.estimated_payments

    @property
    def refund_or_owed(self) -> float:
        """Calculate refund (positive) or amount owed (negative)."""
        return self.total_payments - self.tax_after_credits


@dataclass
class TaxReturn:
    """Complete tax return summary."""
    taxpayer: TaxpayerInfo
    income: TaxableIncome
    tax_year: int = 2025
    federal_calculation: Optional[TaxCalculation] = None
    state_calculation: Optional[TaxCalculation] = None

    # Source documents
    w2_forms: list = field(default_factory=list)
    form_1099_int: list = field(default_factory=list)
    form_1099_div: list = field(default_factory=list)
    form_1099_misc: list = field(default_factory=list)
    form_1099_nec: list = field(default_factory=list)
    form_1099_r: list = field(default_factory=list)
    form_1099_b: list = field(default_factory=list)
    form_1099_g: list = field(default_factory=list)
    form_1098: list = field(default_factory=list)
    form_1098_t: list = field(default_factory=list)

    # Enhanced data
    rental_properties: List[RentalProperty] = field(default_factory=list)
    schedule_a_data: Optional[ScheduleAData] = None
    estimated_payments: List[EstimatedTaxPayment] = field(default_factory=list)
    dependent_care: Optional[DependentCareFSA] = None

    # Computed schedules
    schedule_e_summary: Optional[ScheduleESummary] = None
    schedule_a_result: Optional[ScheduleAResult] = None

    @property
    def total_federal_withheld(self) -> float:
        """Calculate total federal tax withheld from all sources."""
        total = sum(w2.federal_withheld for w2 in self.w2_forms)
        total += sum(f.federal_withheld for f in self.form_1099_int)
        total += sum(f.federal_withheld for f in self.form_1099_div)
        total += sum(f.federal_withheld for f in self.form_1099_misc)
        total += sum(f.federal_withheld for f in self.form_1099_nec)
        total += sum(f.federal_withheld for f in self.form_1099_r)
        return total

    @property
    def total_state_withheld(self) -> float:
        """Calculate total state tax withheld from W-2s and 1099-R."""
        total = sum(w2.state_withheld for w2 in self.w2_forms)
        total += sum(f.state_withheld for f in self.form_1099_r)
        return total

    @property
    def total_mortgage_interest(self) -> float:
        """Calculate total mortgage interest from 1098 forms."""
        return sum(f.mortgage_interest for f in self.form_1098)

    @property
    def total_personal_mortgage_interest(self) -> float:
        """Mortgage interest from personal (non-rental) 1098 forms."""
        return sum(f.mortgage_interest for f in self.form_1098 if not f.is_rental)

    @property
    def total_rental_mortgage_interest(self) -> float:
        """Mortgage interest from rental property 1098 forms."""
        return sum(f.mortgage_interest for f in self.form_1098 if f.is_rental)

    @property
    def total_federal_estimated_payments(self) -> float:
        """Total federal estimated tax payments."""
        return sum(
            p.amount for p in self.estimated_payments
            if p.jurisdiction == "federal"
        )

    @property
    def total_state_estimated_payments(self) -> float:
        """Total state estimated tax payments."""
        return sum(
            p.amount for p in self.estimated_payments
            if p.jurisdiction == "california"
        )

    @property
    def total_medicare_wages(self) -> float:
        """Total Medicare wages from W-2 Box 5."""
        return sum(w2.medicare_wages for w2 in self.w2_forms)

    @property
    def total_us_treasury_interest(self) -> float:
        """Total US Treasury interest (state-exempt) from 1099-INT/DIV forms."""
        total = sum(f.us_treasury_interest for f in self.form_1099_int)
        total += sum(f.us_treasury_interest for f in self.form_1099_div)
        return total

    @property
    def total_dependent_care_benefits(self) -> float:
        """Total dependent care benefits from W-2 Box 10."""
        return sum(w2.dependent_care_benefits for w2 in self.w2_forms)
