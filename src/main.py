"""Main entry point for the tax return tool."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, List

from .models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits, TaxReturn,
    W2Data, Form1099Int, Form1099Div, Form1099Nec, Form1099R, Form1098
)
from .google_drive import GoogleDriveClient
from .document_parser import DocumentParser
from .data_extractor import TaxDataExtractor
from .federal_tax import FederalTaxCalculator
from .california_tax import CaliforniaTaxCalculator


def print_separator(char: str = "=", length: int = 60):
    """Print a separator line."""
    print(char * length)


def format_currency(amount: float) -> str:
    """Format a number as currency."""
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def print_tax_report(tax_return: TaxReturn):
    """Print a formatted tax report."""
    print("\n")
    print_separator()
    print("           TAX RETURN SUMMARY - TAX YEAR 2025")
    print_separator()

    # Taxpayer Info
    print(f"\nTaxpayer: {tax_return.taxpayer.name}")
    print(f"Filing Status: {tax_return.taxpayer.filing_status.value.replace('_', ' ').title()}")

    # Income Summary
    print("\n" + "-" * 40)
    print("INCOME SUMMARY")
    print("-" * 40)
    print(f"  Wages (W-2):              {format_currency(tax_return.income.wages):>15}")
    print(f"  Interest Income:          {format_currency(tax_return.income.interest_income):>15}")
    print(f"  Dividend Income:          {format_currency(tax_return.income.dividend_income):>15}")
    print(f"  Capital Gains:            {format_currency(tax_return.income.capital_gains):>15}")
    print(f"  Retirement (1099-R):      {format_currency(tax_return.income.retirement_income):>15}")
    print(f"  Self-Employment:          {format_currency(tax_return.income.self_employment_income):>15}")
    print(f"  Other Income:             {format_currency(tax_return.income.other_income):>15}")
    print("-" * 40)
    print(f"  TOTAL GROSS INCOME:       {format_currency(tax_return.income.total_income):>15}")

    # Federal Tax
    if tax_return.federal_calculation:
        fed = tax_return.federal_calculation
        print("\n" + "-" * 40)
        print("FEDERAL TAX")
        print("-" * 40)
        print(f"  Adjusted Gross Income:    {format_currency(fed.adjusted_gross_income):>15}")
        print(f"  Deductions:               {format_currency(fed.deductions):>15}")
        print(f"  Taxable Income:           {format_currency(fed.taxable_income):>15}")
        print(f"  Tax Before Credits:       {format_currency(fed.tax_before_credits):>15}")
        print(f"  Tax Credits:              {format_currency(fed.credits):>15}")
        print(f"  Tax After Credits:        {format_currency(fed.tax_after_credits):>15}")
        print(f"  Federal Tax Withheld:     {format_currency(fed.tax_withheld):>15}")
        print("-" * 40)
        refund = fed.refund_or_owed
        if refund >= 0:
            print(f"  FEDERAL REFUND:           {format_currency(refund):>15}")
        else:
            print(f"  FEDERAL TAX OWED:         {format_currency(abs(refund)):>15}")

    # California Tax
    if tax_return.state_calculation:
        state = tax_return.state_calculation
        print("\n" + "-" * 40)
        print("CALIFORNIA STATE TAX")
        print("-" * 40)
        print(f"  CA Adjusted Gross Income: {format_currency(state.adjusted_gross_income):>15}")
        print(f"  CA Deductions:            {format_currency(state.deductions):>15}")
        print(f"  CA Taxable Income:        {format_currency(state.taxable_income):>15}")
        print(f"  CA Tax Before Credits:    {format_currency(state.tax_before_credits):>15}")
        print(f"  CA Tax Credits:           {format_currency(state.credits):>15}")
        print(f"  CA Tax After Credits:     {format_currency(state.tax_after_credits):>15}")
        print(f"  State Tax Withheld:       {format_currency(state.tax_withheld):>15}")
        print("-" * 40)
        refund = state.refund_or_owed
        if refund >= 0:
            print(f"  STATE REFUND:             {format_currency(refund):>15}")
        else:
            print(f"  STATE TAX OWED:           {format_currency(abs(refund)):>15}")

    # Total Summary
    print("\n" + "=" * 40)
    print("TOTAL SUMMARY")
    print("=" * 40)
    fed_refund = tax_return.federal_calculation.refund_or_owed if tax_return.federal_calculation else 0
    state_refund = tax_return.state_calculation.refund_or_owed if tax_return.state_calculation else 0
    total = fed_refund + state_refund
    if total >= 0:
        print(f"  TOTAL REFUND:             {format_currency(total):>15}")
    else:
        print(f"  TOTAL TAX OWED:           {format_currency(abs(total)):>15}")
    print_separator()

    # Disclaimers
    print("\nNOTE: This calculation is for reference only and may not reflect")
    print("actual tax liability. Please consult a tax professional.")
    print("Tax rates are based on 2025 estimates and may change.")


def scan_local_folder(folder_path: str) -> List[str]:
    """
    Recursively scan a local folder for tax documents.

    Args:
        folder_path: Path to the folder to scan

    Returns:
        List of file paths for supported document types
    """
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


def process_tax_documents(
    folder_id: Optional[str] = None,
    credentials_path: str = "config/credentials.json",
    local_files: Optional[list] = None,
    local_folder: Optional[str] = None
) -> TaxReturn:
    """
    Process tax documents and calculate taxes.

    Args:
        folder_id: Google Drive folder ID containing tax documents
        credentials_path: Path to Google OAuth credentials
        local_files: List of local file paths to process (alternative to Drive)
        local_folder: Local folder path to scan recursively

    Returns:
        Completed TaxReturn object
    """
    parser = DocumentParser()
    extractor = TaxDataExtractor()

    # Initialize TaxReturn with default taxpayer
    taxpayer = TaxpayerInfo(name="Taxpayer", filing_status=FilingStatus.SINGLE)
    income = TaxableIncome()
    tax_return = TaxReturn(taxpayer=taxpayer, income=income)

    parsed_docs = []

    # Scan local folder if provided
    if local_folder:
        local_files = scan_local_folder(local_folder)

    # Process files from Google Drive or local
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
            print("Skipping Google Drive integration. Use --files to process local files.")
            return tax_return

    # Extract tax data from documents
    print("\nExtracting tax data...")
    extraction_results = extractor.extract_all(parsed_docs)

    # Aggregate extracted data
    for result in extraction_results:
        if not result.success:
            continue

        if result.form_type == 'W-2':
            w2: W2Data = result.data
            tax_return.w2_forms.append(w2)
            income.wages += w2.wages

        elif result.form_type == '1099-INT':
            form: Form1099Int = result.data
            tax_return.form_1099_int.append(form)
            income.interest_income += form.interest_income

        elif result.form_type == '1099-DIV':
            form: Form1099Div = result.data
            tax_return.form_1099_div.append(form)
            income.dividend_income += form.ordinary_dividends
            income.qualified_dividends += form.qualified_dividends
            income.capital_gains += form.capital_gain_distributions

        elif result.form_type == '1099-NEC':
            form: Form1099Nec = result.data
            tax_return.form_1099_nec.append(form)
            income.self_employment_income += form.nonemployee_compensation

        elif result.form_type == '1099-R':
            form: Form1099R = result.data
            tax_return.form_1099_r.append(form)
            income.retirement_income += form.taxable_amount

        elif result.form_type == '1098':
            form: Form1098 = result.data
            tax_return.form_1098.append(form)

    # Calculate taxes
    print("\nCalculating taxes...")

    # Setup deductions and credits
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    # Federal tax calculation
    fed_calculator = FederalTaxCalculator(taxpayer.filing_status)
    tax_return.federal_calculation = fed_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        federal_withheld=tax_return.total_federal_withheld,
        age=taxpayer.age,
        is_blind=taxpayer.is_blind
    )

    # California tax calculation
    ca_calculator = CaliforniaTaxCalculator(taxpayer.filing_status)
    tax_return.state_calculation = ca_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        state_withheld=tax_return.total_state_withheld,
        num_exemptions=1
    )

    return tax_return


def run_demo():
    """Run a demo with sample data."""
    print("\n" + "=" * 60)
    print("         RUNNING DEMO WITH SAMPLE DATA")
    print("=" * 60)

    # Create sample taxpayer
    taxpayer = TaxpayerInfo(
        name="John Doe",
        filing_status=FilingStatus.SINGLE,
        age=35
    )

    # Create sample W-2
    w2 = W2Data(
        employer_name="Tech Company Inc.",
        wages=120000.00,
        federal_withheld=18500.00,
        social_security_wages=120000.00,
        social_security_tax=7440.00,
        medicare_wages=120000.00,
        medicare_tax=1740.00,
        state="CA",
        state_wages=120000.00,
        state_withheld=7200.00
    )

    # Create sample 1099-INT
    int_form = Form1099Int(
        payer_name="Bank of America",
        interest_income=1500.00
    )

    # Create sample 1099-DIV
    div_form = Form1099Div(
        payer_name="Vanguard",
        ordinary_dividends=3000.00,
        qualified_dividends=2500.00,
        capital_gain_distributions=500.00
    )

    # Build income
    income = TaxableIncome(
        wages=w2.wages,
        interest_income=int_form.interest_income,
        dividend_income=div_form.ordinary_dividends,
        qualified_dividends=div_form.qualified_dividends,
        capital_gains=div_form.capital_gain_distributions
    )

    # Create tax return
    tax_return = TaxReturn(
        taxpayer=taxpayer,
        income=income,
        w2_forms=[w2],
        form_1099_int=[int_form],
        form_1099_div=[div_form]
    )

    # Setup deductions and credits
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    # Calculate Federal tax
    fed_calculator = FederalTaxCalculator(taxpayer.filing_status)
    tax_return.federal_calculation = fed_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        federal_withheld=w2.federal_withheld,
        age=taxpayer.age
    )

    # Calculate California tax
    ca_calculator = CaliforniaTaxCalculator(taxpayer.filing_status)
    tax_return.state_calculation = ca_calculator.calculate(
        income=income,
        deductions=deductions,
        credits=credits,
        state_withheld=w2.state_withheld,
        num_exemptions=1
    )

    # Print report
    print_tax_report(tax_return)

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
        "--files",
        nargs="+",
        help="Local file paths to process (PDF, images, CSV, Excel)"
    )
    parser.add_argument(
        "--local-folder",
        help="Local folder path to scan recursively for tax documents"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with sample demo data"
    )
    parser.add_argument(
        "--filing-status",
        choices=["single", "married_jointly", "married_separately", "head_of_household"],
        default="single",
        help="Tax filing status"
    )

    args = parser.parse_args()

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

    # Process documents
    tax_return = process_tax_documents(
        folder_id=args.folder_id,
        credentials_path=args.credentials,
        local_files=args.files,
        local_folder=args.local_folder
    )

    # Update filing status if specified
    tax_return.taxpayer.filing_status = status_map.get(args.filing_status, FilingStatus.SINGLE)

    # Print report
    print_tax_report(tax_return)


if __name__ == "__main__":
    main()
