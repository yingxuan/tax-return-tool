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

    # ---------------------------------------------------------------
    # Step 2: Prepare Schedule A data
    # ---------------------------------------------------------------
    schedule_a_data = tax_return.schedule_a_data

    # If no explicit Schedule A data but we have 1098 forms, auto-populate
    if not schedule_a_data and tax_return.form_1098:
        schedule_a_data = ScheduleAData(
            mortgage_interest=tax_return.total_mortgage_interest,
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
    )

    # ---------------------------------------------------------------
    # Step 4: California Tax (Form 540)
    # ---------------------------------------------------------------
    ca_calculator = CaliforniaTaxCalculator(
        filing_status=taxpayer.filing_status,
        tax_year=tax_year,
    )
    ca_credits = TaxCredits()  # CA-specific credits are separate

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
    )

    return tax_return


def process_tax_documents(
    folder_id: Optional[str] = None,
    credentials_path: str = "config/credentials.json",
    local_files: Optional[list] = None,
    local_folder: Optional[str] = None,
) -> TaxReturn:
    """Process tax documents from files or Google Drive."""
    parser = DocumentParser()
    extractor = TaxDataExtractor()

    taxpayer = TaxpayerInfo(name="Taxpayer", filing_status=FilingStatus.SINGLE)
    income = TaxableIncome()
    tax_return = TaxReturn(taxpayer=taxpayer, income=income)

    parsed_docs = []

    if local_folder:
        local_files = scan_local_folder(local_folder)

    if local_files:
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
    print("\nExtracting tax data...")
    extraction_results = extractor.extract_all(parsed_docs)

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
            tax_return.form_1098.append(form)

    # Calculate
    print("\nCalculating taxes...")
    tax_return = process_tax_return(tax_return)
    return tax_return


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
        default="single",
        help="Tax filing status"
    )
    parser.add_argument(
        "--tax-year",
        type=int, choices=[2024, 2025], default=2025,
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

    # Map filing status
    status_map = {
        "single": FilingStatus.SINGLE,
        "married_jointly": FilingStatus.MARRIED_FILING_JOINTLY,
        "married_separately": FilingStatus.MARRIED_FILING_SEPARATELY,
        "head_of_household": FilingStatus.HEAD_OF_HOUSEHOLD,
    }

    tax_return = process_tax_documents(
        folder_id=args.folder_id,
        credentials_path=args.credentials,
        local_files=args.files,
        local_folder=args.local_folder,
    )

    tax_return.taxpayer.filing_status = status_map.get(
        args.filing_status, FilingStatus.SINGLE
    )
    tax_return.tax_year = args.tax_year

    # Re-process with correct settings
    tax_return = process_tax_return(tax_return)
    report = generate_full_report(tax_return)
    print(report)


if __name__ == "__main__":
    main()
