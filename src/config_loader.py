"""Load taxpayer profile from a YAML configuration file."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# All US states + DC for state-of-residence selection.
# (code, display_name); states with no general income tax marked for UI.
US_STATES: List[Tuple[str, str]] = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]

# States with no general state income tax (wages); this tool does not calculate state tax for them.
STATES_NO_INCOME_TAX = {"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}


@dataclass
class DependentConfig:
    """A dependent from the config file."""
    name: str = ""
    age: int = 0
    relationship: str = ""
    ssn: Optional[str] = None


@dataclass
class RentalPropertyConfig:
    """Rental property config for fields that cannot be auto-extracted."""
    address: str = ""
    property_type: str = "Single Family"
    purchase_price: float = 0.0
    purchase_date: str = ""  # YYYY-MM-DD
    land_value: float = 0.0
    rental_income: float = 0.0  # Gross rent (not in PM statement)
    insurance: float = 0.0
    property_tax: float = 0.0
    other_expenses: float = 0.0  # Other expenses (gardening, telephone, etc.)
    days_rented: int = 365
    personal_use_days: int = 0


@dataclass
class TaxProfileConfig:
    """Taxpayer profile loaded from YAML."""
    tax_year: int = 2025
    taxpayer_name: str = "Taxpayer"
    taxpayer_ssn: Optional[str] = None
    spouse_ssn: Optional[str] = None
    spouse_name: Optional[str] = None
    filing_status: str = "single"
    age: int = 30
    state_of_residence: str = "CA"  # Two-letter state code; CA = California (only state with calculated tax)
    is_ca_resident: bool = True  # Derived from state_of_residence == "CA"
    is_renter: bool = False
    address_line1: str = ""  # Street address
    address_line2: str = ""  # City, State ZIP
    date_of_birth: str = ""  # MM/DD/YYYY format for PDF forms
    spouse_dob: str = ""  # MM/DD/YYYY format for PDF forms
    county: str = ""  # County of residence (for CA 540)
    dependents: List[DependentConfig] = field(default_factory=list)
    document_folder: Optional[str] = None
    capital_loss_carryover: float = 0.0  # Single total (legacy); use ST/LT split when available
    short_term_loss_carryover: float = 0.0  # Prior-year ST capital loss carryover
    long_term_loss_carryover: float = 0.0  # Prior-year LT capital loss carryover
    personal_mortgage_balance: float = 0.0  # Outstanding principal for debt limit
    us_treasury_interest: float = 0.0  # US Treasury interest (state-exempt)
    charitable_contributions: float = 0.0  # Cash charitable contributions (Schedule A)
    ca_misc_deductions: float = 0.0  # CA-only misc deductions (gross, before 2% AGI floor)
    federal_estimated_payments: float = 0.0  # Federal estimated tax payments made
    ca_estimated_payments: float = 0.0  # CA estimated tax payments made
    federal_withheld_adjustment: float = 0.0  # Correction to auto-extracted federal withholding
    other_income: float = 0.0  # Other income (1099-MISC Box 3, jury duty, etc.)
    qualified_dividends: float = 0.0  # Override: 1099-DIV Box 1b total (if extraction is wrong)
    ordinary_dividends: float = 0.0  # Override: 1099-DIV Box 1a total (if extraction is wrong)
    # Primary residence 2025 property tax total (overrides 1098 + receipts when set)
    primary_property_tax: float = 0.0
    primary_home_apn: str = ""  # APN of primary home (for multi-parcel property tax receipts)
    pal_carryover: float = 0.0  # Prior-year passive activity loss carryover (Form 8582)
    rental_properties: List[RentalPropertyConfig] = field(default_factory=list)


def load_config(path: str) -> Optional[TaxProfileConfig]:
    """
    Load a tax profile from a YAML file.

    Args:
        path: Path to the YAML config file.

    Returns:
        TaxProfileConfig if successful, None otherwise.
    """
    try:
        import yaml
    except ImportError:
        print("Warning: PyYAML is not installed. Run: pip install PyYAML>=6.0")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Config file not found: {path}")
        return None
    except Exception as e:
        print(f"Error reading config file: {e}")
        return None

    if not raw:
        return None

    taxpayer = raw.get("taxpayer", {})
    deps_raw = taxpayer.get("dependents", []) or []
    deps = []
    for d in deps_raw:
        if isinstance(d, str):
            deps.append(DependentConfig(name=d))
        elif isinstance(d, dict):
            deps.append(DependentConfig(
                name=d.get("name", ""),
                age=d.get("age", 0),
                relationship=d.get("relationship", ""),
                ssn=d.get("ssn"),
            ))

    # Parse rental properties
    rentals_raw = raw.get("rental_properties", []) or []
    rental_props = []
    for rp in rentals_raw:
        if isinstance(rp, dict):
            rental_props.append(RentalPropertyConfig(
                address=rp.get("address", ""),
                property_type=rp.get("property_type", "Single Family"),
                purchase_price=float(rp.get("purchase_price", 0.0)),
                purchase_date=str(rp.get("purchase_date", "")),
                land_value=float(rp.get("land_value", 0.0)),
                rental_income=float(rp.get("rental_income", 0.0)),
                insurance=float(rp.get("insurance", 0.0)),
                property_tax=float(rp.get("property_tax", 0.0)),
                other_expenses=float(rp.get("other_expenses", 0.0)),
                days_rented=int(rp.get("days_rented", 365)),
                personal_use_days=int(rp.get("personal_use_days", 0)),
            ))

    state_of_residence = (raw.get("state_of_residence") or taxpayer.get("state_of_residence") or "CA").strip().upper()
    if len(state_of_residence) != 2:
        state_of_residence = "CA"
    is_ca_resident = state_of_residence == "CA"

    config = TaxProfileConfig(
        tax_year=raw.get("tax_year", 2025),
        taxpayer_name=taxpayer.get("name", "Taxpayer"),
        taxpayer_ssn=taxpayer.get("ssn"),
        spouse_ssn=taxpayer.get("spouse_ssn"),
        spouse_name=taxpayer.get("spouse_name"),
        filing_status=taxpayer.get("filing_status", "single"),
        age=taxpayer.get("age", 30),
        state_of_residence=state_of_residence,
        is_ca_resident=is_ca_resident,
        is_renter=taxpayer.get("is_renter", False),
        address_line1=taxpayer.get("address_line1", ""),
        address_line2=taxpayer.get("address_line2", ""),
        date_of_birth=str(taxpayer.get("date_of_birth", "") or ""),
        spouse_dob=str(taxpayer.get("spouse_dob", "") or ""),
        county=str(taxpayer.get("county", "") or ""),
        dependents=deps,
        document_folder=raw.get("document_folder"),
        capital_loss_carryover=float(raw.get("capital_loss_carryover", 0.0)),
        short_term_loss_carryover=float(raw.get("short_term_loss_carryover", 0.0)),
        long_term_loss_carryover=float(raw.get("long_term_loss_carryover", 0.0)),
        personal_mortgage_balance=float(raw.get("personal_mortgage_balance", 0.0)),
        us_treasury_interest=float(raw.get("us_treasury_interest", 0.0)),
        charitable_contributions=float(raw.get("charitable_contributions", 0.0)),
        ca_misc_deductions=float(raw.get("ca_misc_deductions", 0.0)),
        federal_estimated_payments=float(raw.get("federal_estimated_payments", 0.0)),
        ca_estimated_payments=float(raw.get("ca_estimated_payments", 0.0)),
        federal_withheld_adjustment=float(raw.get("federal_withheld_adjustment", 0.0)),
        other_income=float(raw.get("other_income", 0.0)),
        qualified_dividends=float(raw.get("qualified_dividends", 0.0)),
        ordinary_dividends=float(raw.get("ordinary_dividends", 0.0)),
        primary_property_tax=float(raw.get("primary_property_tax", 0.0)),
        pal_carryover=float(raw.get("pal_carryover", 0.0)),
        rental_properties=rental_props,
    )

    # Security warning if SSN fields are present
    has_ssn = config.taxpayer_ssn or config.spouse_ssn or any(d.ssn for d in config.dependents)
    if has_ssn:
        print("\n  WARNING: Config file contains SSN data. "
              "Ensure the config file is gitignored and not shared.")

    return config
