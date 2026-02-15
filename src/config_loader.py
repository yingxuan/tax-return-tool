"""Load taxpayer profile from a YAML configuration file."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DependentConfig:
    """A dependent from the config file."""
    name: str = ""
    age: int = 0
    relationship: str = ""


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
    days_rented: int = 365
    personal_use_days: int = 0


@dataclass
class TaxProfileConfig:
    """Taxpayer profile loaded from YAML."""
    tax_year: int = 2025
    taxpayer_name: str = "Taxpayer"
    filing_status: str = "single"
    age: int = 30
    is_ca_resident: bool = True
    is_renter: bool = False
    dependents: List[DependentConfig] = field(default_factory=list)
    document_folder: Optional[str] = None
    rental_1098_keywords: List[str] = field(default_factory=list)
    capital_loss_carryover: float = 0.0
    personal_mortgage_balance: float = 0.0  # Outstanding principal for debt limit
    us_treasury_interest: float = 0.0  # US Treasury interest (state-exempt)
    charitable_contributions: float = 0.0  # Cash charitable contributions (Schedule A)
    ca_misc_deductions: float = 0.0  # CA-only misc deductions (gross, before 2% AGI floor)
    federal_estimated_payments: float = 0.0  # Federal estimated tax payments made
    ca_estimated_payments: float = 0.0  # CA estimated tax payments made
    federal_withheld_adjustment: float = 0.0  # Correction to auto-extracted federal withholding
    other_income: float = 0.0  # Other income (1099-MISC Box 3, jury duty, etc.)
    # Primary residence 2025 property tax total (overrides 1098 + receipts when set)
    primary_property_tax: float = 0.0
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
                days_rented=int(rp.get("days_rented", 365)),
                personal_use_days=int(rp.get("personal_use_days", 0)),
            ))

    return TaxProfileConfig(
        tax_year=raw.get("tax_year", 2025),
        taxpayer_name=taxpayer.get("name", "Taxpayer"),
        filing_status=taxpayer.get("filing_status", "single"),
        age=taxpayer.get("age", 30),
        is_ca_resident=taxpayer.get("is_ca_resident", True),
        is_renter=taxpayer.get("is_renter", False),
        dependents=deps,
        document_folder=raw.get("document_folder"),
        rental_1098_keywords=[
            kw.lower() for kw in (raw.get("rental_1098_keywords") or [])
        ],
        capital_loss_carryover=float(raw.get("capital_loss_carryover", 0.0)),
        personal_mortgage_balance=float(raw.get("personal_mortgage_balance", 0.0)),
        us_treasury_interest=float(raw.get("us_treasury_interest", 0.0)),
        charitable_contributions=float(raw.get("charitable_contributions", 0.0)),
        ca_misc_deductions=float(raw.get("ca_misc_deductions", 0.0)),
        federal_estimated_payments=float(raw.get("federal_estimated_payments", 0.0)),
        ca_estimated_payments=float(raw.get("ca_estimated_payments", 0.0)),
        federal_withheld_adjustment=float(raw.get("federal_withheld_adjustment", 0.0)),
        other_income=float(raw.get("other_income", 0.0)),
        primary_property_tax=float(raw.get("primary_property_tax", 0.0)),
        rental_properties=rental_props,
    )
