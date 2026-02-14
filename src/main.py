"""Main entry point for the tax return tool."""

import argparse
from datetime import date
from pathlib import Path
from typing import Optional, List

from .models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits,
    TaxReturn, W2Data, Form1099Int, Form1099Div, Form1099Nec, Form1099R,
    Form1098, Dependent, RentalProperty, ScheduleAData, CAVehicleRegistration,
    EstimatedTaxPayment, DependentCareFSA,
)
from .google_drive import GoogleDriveClient
from .document_parser import DocumentParser
from .data_extractor import TaxDataExtractor
from .federal_tax import FederalTaxCalculator
from .california_tax import CaliforniaTaxCalculator
from .schedule_e import ScheduleECalculator
from .schedule_a import ScheduleACalculator
from .report_generator import generate_full_report
from .file_watcher import TaxDocumentWatcher
from .config_loader import load_config, TaxProfileConfig


# Map config / CLI filing status strings to enum
STATUS_MAP = {
    "single": FilingStatus.SINGLE,
    "married_jointly": FilingStatus.MARRIED_FILING_JOINTLY,
    "married_filing_jointly": FilingStatus.MARRIED_FILING_JOINTLY,
    "married_separately": FilingStatus.MARRIED_FILING_SEPARATELY,
    "married_filing_separately": FilingStatus.MARRIED_FILING_SEPARATELY,
    "head_of_household": FilingStatus.HEAD_OF_HOUSEHOLD,
}


def scan_local_folder(folder_path: str) -> List[str]:
    """Recursively scan a local folder for tax documents."""
    supported_extensions = {
        '.pdf', '.csv', '.xlsx', '.xls',
        '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'
    }

    files = []
    folder = Path(folder_path)

    if not folder.exists():
        print(f"Error: Folder not found: {folder_path}")
        return files

    print(f"\nScanning folder: {folder_path}")
    for file_path in folder.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            files.append(str(file_path))
            print(f"  Found: {file_path.relative_to(folder)}")

    print(f"\nTotal files found: {len(files)}")
    return files


def scan_and_categorize_folder(folder_path: str) -> dict:
    """
    Scan a folder using TaxDocumentWatcher for folder-aware categorization.

    Prints a categorized inventory and returns the summary dict.
    """
    watcher = TaxDocumentWatcher(folder_path)
    summary = watcher.get_summary()
    TaxDocumentWatcher.print_summary(summary)
    return summary


def process_tax_return(tax_return: TaxReturn) -> TaxReturn:
    """
    Run all calculations on a populated TaxReturn.

    This is the main orchestration function that:
    1. Computes Schedule E (rental properties)
    2. Sets up Schedule A data from source forms
    3. Runs federal tax calculation
    4. Runs California tax calculation
    """
    taxpayer = tax_return.taxpayer
    income = tax_return.income
    tax_year = tax_return.tax_year

    # ---------------------------------------------------------------
    # Step 1: Schedule E - Rental Properties
    # ---------------------------------------------------------------
    schedule_e_summary = None
    if tax_return.rental_properties:
        sched_e = ScheduleECalculator(tax_year=tax_year)
        schedule_e_summary = sched_e.calculate_all(tax_return.rental_properties)
        tax_return.schedule_e_summary = schedule_e_summary
        # Flow net rental income into TaxableIncome
        income.rental_income = schedule_e_summary.total_net_rental_income

        # Passive Activity Loss Limitations (Form 8582)
        # The $25,000 special allowance for rental real estate phases out
        # completely at MAGI > $150K.  Estimate MAGI without rental loss.
        if income.rental_income < 0:
            preliminary_agi = income.total_income - income.rental_income
            if preliminary_agi > 150_000:
                income.rental_income = 0  # Disallow passive rental losses

    # ---------------------------------------------------------------
    # Step 2: Prepare Schedule A data
    # ---------------------------------------------------------------
    schedule_a_data = tax_return.schedule_a_data

    # If no explicit Schedule A data, auto-populate from source documents.
    # Only use personal (non-rental) mortgage interest for Schedule A;
    # rental mortgage interest flows through Schedule E instead.
    if not schedule_a_data:
        # State income tax paid = W-2 state withholding + 1099-R state withholding
        state_income_tax_paid = (
            sum(w2.state_withheld for w2 in tax_return.w2_forms)
            + sum(f.state_withheld for f in tax_return.form_1099_r)
            + tax_return.total_state_estimated_payments
        )

        # Property taxes from personal (non-rental) 1098 forms
        real_estate_taxes = sum(
            f.property_taxes for f in tax_return.form_1098 if not f.is_rental
        )

        mortgage_interest = tax_return.total_personal_mortgage_interest

        # Only create Schedule A data if we have meaningful inputs
        if mortgage_interest > 0 or state_income_tax_paid > 0 or real_estate_taxes > 0:
            schedule_a_data = ScheduleAData(
                state_income_tax_paid=state_income_tax_paid,
                real_estate_taxes=real_estate_taxes,
                mortgage_interest=mortgage_interest,
            )

    # ---------------------------------------------------------------
    # Step 3: Federal Tax (Form 1040)
    # ---------------------------------------------------------------
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    fed_calculator = FederalTaxCalculator(
        filing_status=taxpayer.filing_status,
        tax_year=tax_year,
    )

    # Use Medicare wages (W-2 box 5) for Additional Medicare Tax if available
    medicare_wages = tax_return.total_medicare_wages or None

    tax_return.federal_calculation = fed_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        federal_withheld=tax_return.total_federal_withheld,
        age=taxpayer.age,
        is_blind=taxpayer.is_blind,
        num_qualifying_children=taxpayer.num_qualifying_children,
        schedule_a_data=schedule_a_data,
        schedule_e_summary=schedule_e_summary,
        estimated_payments=tax_return.total_federal_estimated_payments,
        medicare_wages=medicare_wages,
    )

    # ---------------------------------------------------------------
    # Step 4: California Tax (Form 540)
    # ---------------------------------------------------------------
    ca_calculator = CaliforniaTaxCalculator(
        filing_status=taxpayer.filing_status,
        tax_year=tax_year,
    )
    ca_credits = TaxCredits()  # CA-specific credits are separate

    # Pass federal AGI for CA exemption credit phaseout
    federal_agi = tax_return.federal_calculation.adjusted_gross_income

    tax_return.state_calculation = ca_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=ca_credits,
        state_withheld=tax_return.total_state_withheld,
        num_exemptions=taxpayer.num_exemptions,
        is_renter=taxpayer.is_renter,
        schedule_a_data=schedule_a_data,
        schedule_e_summary=schedule_e_summary,
        estimated_payments=tax_return.total_state_estimated_payments,
        us_treasury_interest=tax_return.total_us_treasury_interest,
        federal_agi=federal_agi,
    )

    return tax_return


def _build_taxpayer_from_config(config: TaxProfileConfig) -> TaxpayerInfo:
    """Create a TaxpayerInfo from a config profile."""
    filing_status = STATUS_MAP.get(
        config.filing_status, FilingStatus.SINGLE
    )
    deps = [
        Dependent(name=d.name, age=d.age, relationship=d.relationship)
        for d in config.dependents
    ]
    return TaxpayerInfo(
        name=config.taxpayer_name,
        filing_status=filing_status,
        age=config.age,
        is_ca_resident=config.is_ca_resident,
        is_renter=config.is_renter,
        dependents=deps,
    )


def process_tax_documents(
    folder_id: Optional[str] = None,
    credentials_path: str = "config/credentials.json",
    local_files: Optional[list] = None,
    local_folder: Optional[str] = None,
    config: Optional[TaxProfileConfig] = None,
) -> TaxReturn:
    """Process tax documents from files or Google Drive."""
    parser = DocumentParser()
    extractor = TaxDataExtractor()

    # Build taxpayer from config or defaults
    if config:
        taxpayer = _build_taxpayer_from_config(config)
        tax_year = config.tax_year
    else:
        taxpayer = TaxpayerInfo(name="Taxpayer", filing_status=FilingStatus.SINGLE)
        tax_year = 2025

    income = TaxableIncome()
    tax_return = TaxReturn(taxpayer=taxpayer, income=income, tax_year=tax_year)

    parsed_docs = []
    category_hints = {}  # file path -> category from folder scan

    # Determine the document folder
    doc_folder = local_folder or (config.document_folder if config else None)

    if doc_folder:
        # Use folder-aware categorization to print inventory
        summary = scan_and_categorize_folder(doc_folder)

        # Collect all files for parsing (OCR/text extraction)
        all_files = []
        for category, files in summary.items():
            for f in files:
                all_files.append(f.path)
                category_hints[f.path] = category

        if all_files:
            print(f"\nProcessing {len(all_files)} document(s) through OCR/parsing...")
            parsed_docs = parser.parse_multiple(all_files)
        else:
            print("\nNo documents found.")
    elif local_files:
        print("\nProcessing local files...")
        parsed_docs = parser.parse_multiple(local_files)
    elif folder_id or credentials_path:
        try:
            print("\nConnecting to Google Drive...")
            drive = GoogleDriveClient(credentials_path=credentials_path)
            downloaded = drive.download_all_tax_documents(folder_id)
            file_paths = [d['path'] for d in downloaded]
            parsed_docs = parser.parse_multiple(file_paths)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Skipping Google Drive. Use --files to process local files.")
            return tax_return

    # Extract tax data
    if parsed_docs:
        print("\nExtracting tax data...")
        extraction_results = extractor.extract_all(parsed_docs, category_hints=category_hints)

        for result in extraction_results:
            if not result.success:
                continue

            if result.form_type == 'W-2':
                w2 = result.data
                tax_return.w2_forms.append(w2)
                income.wages += w2.wages
            elif result.form_type == '1099-INT':
                form = result.data
                tax_return.form_1099_int.append(form)
                income.interest_income += form.interest_income
            elif result.form_type == '1099-DIV':
                form = result.data
                tax_return.form_1099_div.append(form)
                income.dividend_income += form.ordinary_dividends
                income.qualified_dividends += form.qualified_dividends
                income.capital_gains += form.capital_gain_distributions
            elif result.form_type == '1099-NEC':
                form = result.data
                tax_return.form_1099_nec.append(form)
                income.self_employment_income += form.nonemployee_compensation
            elif result.form_type == '1099-R':
                form = result.data
                tax_return.form_1099_r.append(form)
                income.retirement_income += form.taxable_amount
            elif result.form_type == '1098':
                form = result.data
                # Tag rental 1098s based on config keywords
                # Match against lender name, property address (Box 8),
                # source file path, and full document text
                if config and config.rental_1098_keywords:
                    searchable = " ".join([
                        form.lender_name,
                        form.property_address,
                        result.source_file,
                        result.source_text,
                    ]).lower()
                    for kw in config.rental_1098_keywords:
                        if kw in searchable:
                            form.is_rental = True
                            break
                tax_return.form_1098.append(form)

    # Apply US Treasury interest from config (state-exempt)
    if config and config.us_treasury_interest > 0:
        # Track as a synthetic 1099-INT with treasury interest only
        # (the interest is already included in income from actual 1099 forms)
        treasury_marker = Form1099Int(
            payer_name="US Treasury (config)",
            interest_income=0.0,  # Already counted in actual 1099-INT
            us_treasury_interest=config.us_treasury_interest,
        )
        tax_return.form_1099_int.append(treasury_marker)

    # Apply capital loss carryover from prior year (capped at $3K for MFJ/Single, $1.5K for MFS)
    if config and config.capital_loss_carryover > 0:
        if taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY:
            cap = 1_500
        else:
            cap = 3_000
        loss = min(config.capital_loss_carryover, cap)
        income.capital_gains -= loss

    # Apply other income from config (e.g. 1099-MISC Box 3 not auto-extracted)
    if config and config.other_income != 0:
        income.other_income += config.other_income

    # Apply dividend adjustment from config (e.g. exclude forms not in CPA return)
    if config and config.dividend_adjustment != 0:
        income.dividend_income += config.dividend_adjustment

    # Apply estimated tax payments from config (before schedule_a_data creation,
    # because CA estimated payments count towards state_income_tax_paid for SALT)
    if config and config.federal_estimated_payments > 0:
        tax_return.estimated_payments.append(EstimatedTaxPayment(
            amount=config.federal_estimated_payments,
            period="Total",
            jurisdiction="federal",
        ))
    if config and config.ca_estimated_payments > 0:
        tax_return.estimated_payments.append(EstimatedTaxPayment(
            amount=config.ca_estimated_payments,
            period="Total",
            jurisdiction="california",
        ))

    # Apply federal withholding adjustment from config
    if config and config.federal_withheld_adjustment != 0:
        tax_return.federal_withheld_adjustment = config.federal_withheld_adjustment

    # Set mortgage balance from config on schedule_a_data
    if config and config.personal_mortgage_balance > 0:
        balance = config.personal_mortgage_balance

        # Validate: a personal mortgage balance over $10M is almost certainly a
        # config error (e.g. value entered in cents instead of dollars, or
        # extra zeros).  Warn loudly but still proceed.
        if balance > 10_000_000:
            print(
                f"\n  *** WARNING: personal_mortgage_balance = ${balance:,.0f} "
                f"seems unrealistically high. ***"
                f"\n  *** If this is in cents, divide by 100.  A $2.7M balance "
                f"should be entered as 2700000, not 270000000. ***"
                f"\n  *** Current value causes mortgage interest to be prorated "
                f"to {750_000 / balance * 100:.2f}% (federal) / "
                f"{1_000_000 / balance * 100:.2f}% (CA). ***\n"
            )

        if not tax_return.schedule_a_data:
            # Pre-build schedule_a_data so process_tax_return uses it
            state_income_tax_paid = (
                sum(w2.state_withheld for w2 in tax_return.w2_forms)
                + sum(f.state_withheld for f in tax_return.form_1099_r)
                + tax_return.total_state_estimated_payments
            )
            real_estate_taxes = sum(
                f.property_taxes for f in tax_return.form_1098 if not f.is_rental
            )
            tax_return.schedule_a_data = ScheduleAData(
                state_income_tax_paid=state_income_tax_paid,
                real_estate_taxes=real_estate_taxes,
                mortgage_interest=tax_return.total_personal_mortgage_interest,
                mortgage_balance=balance,
            )
        else:
            tax_return.schedule_a_data.mortgage_balance = balance

    # Apply charitable contributions from config
    if config and config.charitable_contributions > 0 and tax_return.schedule_a_data:
        tax_return.schedule_a_data.cash_contributions += config.charitable_contributions

    # Apply CA-only miscellaneous deductions from config
    if config and config.ca_misc_deductions > 0 and tax_return.schedule_a_data:
        tax_return.schedule_a_data.ca_misc_deductions = config.ca_misc_deductions

    # Print data ingestion summary for debugging
    _print_ingestion_summary(tax_return, config)

    # Calculate
    print("\nCalculating taxes...")
    tax_return = process_tax_return(tax_return)
    return tax_return


def _print_ingestion_summary(tax_return: TaxReturn, config) -> None:
    """Print a summary of ingested data to help catch parsing issues."""
    fmt = lambda x: f"${x:,.2f}"
    inc = tax_return.income

    print("\n" + "-" * 60)
    print("  DATA INGESTION SUMMARY")
    print("-" * 60)
    print(f"  W-2 forms:       {len(tax_return.w2_forms)}")
    print(f"  1099-INT forms:  {len(tax_return.form_1099_int)}")
    print(f"  1099-DIV forms:  {len(tax_return.form_1099_div)}")
    print(f"  1099-NEC forms:  {len(tax_return.form_1099_nec)}")
    print(f"  1099-R forms:    {len(tax_return.form_1099_r)}")
    print(f"  1098 forms:      {len(tax_return.form_1098)}"
          f" ({sum(1 for f in tax_return.form_1098 if not f.is_rental)} personal,"
          f" {sum(1 for f in tax_return.form_1098 if f.is_rental)} rental)")

    print(f"\n  Wages:                     {fmt(inc.wages)}")
    print(f"  Interest income:           {fmt(inc.interest_income)}")
    print(f"  Ordinary dividends:        {fmt(inc.dividend_income)}")
    print(f"  Qualified dividends:       {fmt(inc.qualified_dividends)}")
    print(f"  Capital gains:             {fmt(inc.capital_gains)}")
    print(f"  Self-employment:           {fmt(inc.self_employment_income)}")
    print(f"  Retirement:                {fmt(inc.retirement_income)}")

    pers_int = tax_return.total_personal_mortgage_interest
    rent_int = tax_return.total_rental_mortgage_interest
    pers_prop_tax = sum(f.property_taxes for f in tax_return.form_1098 if not f.is_rental)
    print(f"\n  Personal mortgage interest:{fmt(pers_int)}")
    print(f"  Rental mortgage interest:  {fmt(rent_int)}")
    print(f"  Personal property taxes:   {fmt(pers_prop_tax)}")
    print(f"  State withholding (W-2):   {fmt(sum(w.state_withheld for w in tax_return.w2_forms))}")
    print(f"  State withholding (1099-R):{fmt(sum(f.state_withheld for f in tax_return.form_1099_r))}")

    if config and config.personal_mortgage_balance > 0:
        bal = config.personal_mortgage_balance
        print(f"\n  Mortgage balance (config): {fmt(bal)}")
        if bal > 750_000:
            fed_pct = 750_000 / bal * 100
            ca_pct = min(1_000_000 / bal, 1.0) * 100
            print(f"  Federal proration:         {fed_pct:.2f}%  -> {fmt(pers_int * 750_000 / bal)}")
            print(f"  CA proration:              {ca_pct:.2f}%  -> {fmt(pers_int * min(1_000_000 / bal, 1.0))}")

    if inc.dividend_income == 0 and inc.qualified_dividends == 0:
        print("\n  *** NOTE: No dividend income detected. If you have 1099-DIV")
        print("  *** documents, check that OCR/parsing extracted them correctly.")
    print("-" * 60)


def run_demo():
    """Run a comprehensive demo with a complex tax profile."""
    print("\n" + "=" * 72)
    print("  RUNNING COMPREHENSIVE DEMO - Complex Tax Profile")
    print("=" * 72)

    tax_year = 2025

    # -------------------------------------------------------------------
    # Taxpayer: Married Filing Jointly, 2 kids
    # -------------------------------------------------------------------
    taxpayer = TaxpayerInfo(
        name="John & Jane Doe",
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        age=42,
        is_ca_resident=True,
        is_renter=False,  # They own a home
        dependents=[
            Dependent(name="Emily Doe", age=11, relationship="daughter"),
            Dependent(name="Michael Doe", age=14, relationship="son"),
        ],
    )

    # -------------------------------------------------------------------
    # W-2 Income
    # -------------------------------------------------------------------
    w2_john = W2Data(
        employer_name="Tech Corp Inc.",
        wages=185_000.00,
        federal_withheld=32_000.00,
        social_security_wages=176_100.00,
        social_security_tax=10_918.20,
        medicare_wages=185_000.00,
        medicare_tax=2_682.50,
        dependent_care_benefits=5_000.00,  # Dependent Care FSA
        state="CA",
        state_wages=185_000.00,
        state_withheld=14_200.00,
    )

    w2_jane = W2Data(
        employer_name="Healthcare Partners LLC",
        wages=95_000.00,
        federal_withheld=14_500.00,
        social_security_wages=95_000.00,
        social_security_tax=5_890.00,
        medicare_wages=95_000.00,
        medicare_tax=1_377.50,
        state="CA",
        state_wages=95_000.00,
        state_withheld=6_800.00,
    )

    # -------------------------------------------------------------------
    # Investment Income
    # -------------------------------------------------------------------
    int_form = Form1099Int(
        payer_name="Chase Bank",
        interest_income=2_800.00,
    )

    div_form = Form1099Div(
        payer_name="Vanguard Brokerage",
        ordinary_dividends=4_500.00,
        qualified_dividends=3_800.00,
        capital_gain_distributions=1_200.00,
    )

    # -------------------------------------------------------------------
    # Side Hustle Income (1099-NEC)
    # -------------------------------------------------------------------
    nec_form = Form1099Nec(
        payer_name="Consulting Client LLC",
        nonemployee_compensation=12_000.00,
    )

    # -------------------------------------------------------------------
    # Rental Property (Schedule E)
    # -------------------------------------------------------------------
    rental = RentalProperty(
        address="456 Oak Avenue, Sacramento, CA 95814",
        property_type="Single Family",
        purchase_price=420_000.00,
        purchase_date=date(2020, 6, 15),
        land_value=100_000.00,  # Land portion not depreciable
        days_rented=365,
        personal_use_days=0,
        rental_income=30_000.00,  # $2,500/month
        management_fees=3_000.00,  # 10% of rent
        property_tax=4_200.00,
        insurance=1_800.00,
        repairs=2_500.00,
        mortgage_interest=8_400.00,
        utilities=0.0,  # Tenant pays
    )

    # -------------------------------------------------------------------
    # Primary Residence Mortgage (1098)
    # -------------------------------------------------------------------
    mortgage_form = Form1098(
        lender_name="Wells Fargo Home Mortgage",
        mortgage_interest=18_500.00,
        property_taxes=9_200.00,
    )

    # -------------------------------------------------------------------
    # Schedule A (Itemized Deductions)
    # -------------------------------------------------------------------
    schedule_a = ScheduleAData(
        # Medical
        medical_expenses=3_500.00,

        # Taxes
        state_income_tax_paid=21_000.00,  # CA withholding from both W-2s
        real_estate_taxes=9_200.00,  # From 1098
        personal_property_taxes=0.0,
        vehicle_registrations=[
            CAVehicleRegistration(
                total_registration_fee=450.00,
                vehicle_license_fee=285.00,  # The deductible VLF portion
                weight_fee=65.00,
                other_fees=100.00,
            ),
            CAVehicleRegistration(
                total_registration_fee=380.00,
                vehicle_license_fee=225.00,
                weight_fee=55.00,
                other_fees=100.00,
            ),
        ],

        # Interest
        mortgage_interest=18_500.00,

        # Charitable
        cash_contributions=6_000.00,
        noncash_contributions=1_500.00,
    )

    # -------------------------------------------------------------------
    # Dependent Care FSA (Form 2441)
    # -------------------------------------------------------------------
    dependent_care = DependentCareFSA(
        provider_name="Kids Care Center",
        amount_paid=8_000.00,
        fsa_contribution=5_000.00,  # Pre-tax from W-2 Box 10
    )

    # -------------------------------------------------------------------
    # Estimated Tax Payments
    # -------------------------------------------------------------------
    estimated_payments = [
        EstimatedTaxPayment(payment_date=date(2025, 4, 15), amount=3_000.00, period="Q1", jurisdiction="federal"),
        EstimatedTaxPayment(payment_date=date(2025, 6, 15), amount=3_000.00, period="Q2", jurisdiction="federal"),
        EstimatedTaxPayment(payment_date=date(2025, 9, 15), amount=3_000.00, period="Q3", jurisdiction="federal"),
        EstimatedTaxPayment(payment_date=date(2026, 1, 15), amount=3_000.00, period="Q4", jurisdiction="federal"),
        EstimatedTaxPayment(payment_date=date(2025, 4, 15), amount=1_500.00, period="Q1", jurisdiction="california"),
        EstimatedTaxPayment(payment_date=date(2025, 6, 15), amount=1_500.00, period="Q2", jurisdiction="california"),
        EstimatedTaxPayment(payment_date=date(2025, 9, 15), amount=1_500.00, period="Q3", jurisdiction="california"),
        EstimatedTaxPayment(payment_date=date(2026, 1, 15), amount=1_500.00, period="Q4", jurisdiction="california"),
    ]

    # -------------------------------------------------------------------
    # Build income
    # -------------------------------------------------------------------
    income = TaxableIncome(
        wages=w2_john.wages + w2_jane.wages,
        interest_income=int_form.interest_income,
        dividend_income=div_form.ordinary_dividends,
        qualified_dividends=div_form.qualified_dividends,
        capital_gains=div_form.capital_gain_distributions,
        self_employment_income=nec_form.nonemployee_compensation,
        # rental_income will be computed by Schedule E
    )

    # -------------------------------------------------------------------
    # Assemble TaxReturn
    # -------------------------------------------------------------------
    tax_return = TaxReturn(
        taxpayer=taxpayer,
        income=income,
        tax_year=tax_year,
        w2_forms=[w2_john, w2_jane],
        form_1099_int=[int_form],
        form_1099_div=[div_form],
        form_1099_nec=[nec_form],
        form_1098=[mortgage_form],
        rental_properties=[rental],
        schedule_a_data=schedule_a,
        estimated_payments=estimated_payments,
        dependent_care=dependent_care,
    )

    # -------------------------------------------------------------------
    # Process and generate report
    # -------------------------------------------------------------------
    tax_return = process_tax_return(tax_return)
    report = generate_full_report(tax_return)
    print(report)

    return tax_return


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tax Return Tool - Calculate Federal and California taxes"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: config/tax_profile.yaml)"
    )
    parser.add_argument(
        "--folder-id",
        help="Google Drive folder ID containing tax documents"
    )
    parser.add_argument(
        "--credentials",
        default="config/credentials.json",
        help="Path to Google OAuth credentials file"
    )
    parser.add_argument(
        "--files", nargs="+",
        help="Local file paths to process (PDF, images, CSV, Excel)"
    )
    parser.add_argument(
        "--local-folder",
        help="Local folder path to scan recursively for tax documents"
    )
    parser.add_argument(
        "--watch",
        help="Watch a directory for new tax documents"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with comprehensive sample demo data"
    )
    parser.add_argument(
        "--filing-status",
        choices=["single", "married_jointly", "married_separately", "head_of_household"],
        default=None,
        help="Tax filing status"
    )
    parser.add_argument(
        "--tax-year",
        type=int, choices=[2024, 2025], default=None,
        help="Target tax year (2024 or 2025)"
    )

    args = parser.parse_args()

    # Watch mode
    if args.watch:
        print(f"\nWatching directory: {args.watch}")
        watcher = TaxDocumentWatcher(args.watch)
        summary = watcher.get_summary()
        TaxDocumentWatcher.print_summary(summary)
        return

    if args.demo:
        run_demo()
        return

    # Load config if specified
    config = None
    if args.config:
        config = load_config(args.config)
        if config:
            print(f"\nLoaded config: {args.config}")
            print(f"  Taxpayer: {config.taxpayer_name}")
            print(f"  Filing status: {config.filing_status}")
            print(f"  Tax year: {config.tax_year}")
            if config.document_folder:
                print(f"  Document folder: {config.document_folder}")

    # Process documents
    tax_return = process_tax_documents(
        folder_id=args.folder_id,
        credentials_path=args.credentials,
        local_files=args.files,
        local_folder=args.local_folder,
        config=config,
    )

    # CLI overrides take precedence over config
    if args.filing_status:
        tax_return.taxpayer.filing_status = STATUS_MAP.get(
            args.filing_status, FilingStatus.SINGLE
        )
    if args.tax_year:
        tax_return.tax_year = args.tax_year

    # Re-process if CLI overrides were applied
    if args.filing_status or args.tax_year:
        tax_return = process_tax_return(tax_return)

    report = generate_full_report(tax_return)
    print(report)


if __name__ == "__main__":
    main()
