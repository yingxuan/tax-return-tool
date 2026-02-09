"""Data models for tax return information."""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class FilingStatus(Enum):
    """Tax filing status options."""
    SINGLE = "single"
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"


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
    state: Optional[str] = None  # Box 15
    state_wages: float = 0.0  # Box 16
    state_withheld: float = 0.0  # Box 17


@dataclass
class Form1099Int:
    """1099-INT form data for interest income."""
    payer_name: str
    interest_income: float = 0.0  # Box 1
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099Div:
    """1099-DIV form data for dividend income."""
    payer_name: str
    ordinary_dividends: float = 0.0  # Box 1a
    qualified_dividends: float = 0.0  # Box 1b
    capital_gain_distributions: float = 0.0  # Box 2a
    federal_withheld: float = 0.0  # Box 4


@dataclass
class Form1099Misc:
    """1099-MISC form data for miscellaneous income."""
    payer_name: str
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
    federal_withheld: float = 0.0  # Box 4
    state_withheld: float = 0.0  # Box 12


@dataclass
class Form1099B:
    """1099-B form data for broker transactions."""
    broker_name: str
    proceeds: float = 0.0  # Total proceeds
    cost_basis: float = 0.0  # Total cost basis
    gain_loss: float = 0.0  # Net gain/loss


@dataclass
class Form1098:
    """1098 form data for mortgage interest."""
    lender_name: str
    mortgage_interest: float = 0.0  # Box 1
    property_taxes: float = 0.0  # Box 10 (if reported)


@dataclass
class TaxpayerInfo:
    """Basic taxpayer information."""
    name: str
    ssn: Optional[str] = None
    filing_status: FilingStatus = FilingStatus.SINGLE
    age: int = 30
    is_blind: bool = False


@dataclass
class TaxableIncome:
    """Breakdown of taxable income sources."""
    wages: float = 0.0
    interest_income: float = 0.0
    dividend_income: float = 0.0
    qualified_dividends: float = 0.0
    capital_gains: float = 0.0
    other_income: float = 0.0
    self_employment_income: float = 0.0
    retirement_income: float = 0.0  # From 1099-R

    @property
    def total_income(self) -> float:
        """Calculate total gross income."""
        return (
            self.wages +
            self.interest_income +
            self.dividend_income +
            self.capital_gains +
            self.other_income +
            self.self_employment_income +
            self.retirement_income
        )


@dataclass
class Deductions:
    """Tax deductions."""
    standard_deduction: float = 0.0
    itemized_deductions: float = 0.0
    use_standard: bool = True

    # Itemized deduction breakdown
    state_local_taxes: float = 0.0  # SALT, capped at $10,000
    mortgage_interest: float = 0.0
    charitable_contributions: float = 0.0
    medical_expenses: float = 0.0

    @property
    def total_deductions(self) -> float:
        """Get the applicable deduction amount."""
        if self.use_standard:
            return self.standard_deduction
        return self.itemized_deductions


@dataclass
class TaxCredits:
    """Tax credits that reduce tax liability."""
    child_tax_credit: float = 0.0
    earned_income_credit: float = 0.0
    education_credits: float = 0.0
    other_credits: float = 0.0

    @property
    def total_credits(self) -> float:
        """Calculate total credits."""
        return (
            self.child_tax_credit +
            self.earned_income_credit +
            self.education_credits +
            self.other_credits
        )


@dataclass
class TaxCalculation:
    """Result of tax calculation for a single jurisdiction."""
    jurisdiction: str  # "Federal" or "California"
    gross_income: float
    adjustments: float
    adjusted_gross_income: float
    deductions: float
    taxable_income: float
    tax_before_credits: float
    credits: float
    tax_after_credits: float
    tax_withheld: float

    @property
    def refund_or_owed(self) -> float:
        """Calculate refund (positive) or amount owed (negative)."""
        return self.tax_withheld - self.tax_after_credits


@dataclass
class TaxReturn:
    """Complete tax return summary."""
    taxpayer: TaxpayerInfo
    income: TaxableIncome
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
    form_1098: list = field(default_factory=list)

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
