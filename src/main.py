"""Main entry point for the tax return tool."""

import argparse
from datetime import date
from pathlib import Path
from typing import Optional, List

from .models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits,
    TaxReturn, W2Data, Form1099Int, Form1099Div, Form1099Nec, Form1099R,
    Form1099B, Form1098, Dependent, RentalProperty, ScheduleAData,
    CAVehicleRegistration, EstimatedTaxPayment, DependentCareFSA,
    MiscDeductionDoc,
)
from .document_parser import DocumentParser
from .data_extractor import TaxDataExtractor
from .federal_tax import FederalTaxCalculator
from .state_tax import calculate_state_tax
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
        # Include prior-year PAL carryover from config.
        prior_pal = tax_return.prior_pal_carryover
        # Net passive activity: current rental income minus prior unallowed losses
        net_passive = income.rental_income - prior_pal

        if net_passive < 0:
            # Net passive loss — apply PAL limitation rules
            net_loss = abs(net_passive)
            preliminary_agi = income.total_income - income.rental_income
            if preliminary_agi > 150_000:
                # Full disallowance: no special allowance
                income.rental_income = 0
                schedule_e_summary.pal_disallowed = net_loss
                schedule_e_summary.pal_carryover = net_loss
            elif preliminary_agi > 100_000:
                # Phase-out: $25K allowance reduced by 50% of (MAGI - $100K)
                allowance = max(0, 25_000 - (preliminary_agi - 100_000) * 0.5)
                allowed = min(allowance, net_loss)
                income.rental_income = -allowed
                schedule_e_summary.pal_disallowed = net_loss - allowed
                schedule_e_summary.pal_carryover = net_loss - allowed
            else:
                # Below $100K AGI: full $25K allowance
                allowance = 25_000
                allowed = min(allowance, net_loss)
                income.rental_income = -allowed
                schedule_e_summary.pal_disallowed = net_loss - allowed
                schedule_e_summary.pal_carryover = net_loss - allowed
        elif prior_pal > 0 and net_passive >= 0:
            # Current rental gain absorbs all prior PAL; net is still positive
            # Report the net gain (prior PAL fully used)
            income.rental_income = net_passive
            schedule_e_summary.pal_disallowed = 0
            schedule_e_summary.pal_carryover = 0

    # ---------------------------------------------------------------
    # Step 2: Prepare Schedule A data
    # ---------------------------------------------------------------
    schedule_a_data = tax_return.schedule_a_data
    personal_mortgage_interest = tax_return.total_personal_mortgage_interest

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

        # Only create Schedule A data if we have meaningful inputs
        if personal_mortgage_interest > 0 or state_income_tax_paid > 0 or real_estate_taxes > 0:
            schedule_a_data = ScheduleAData(
                state_income_tax_paid=state_income_tax_paid,
                real_estate_taxes=real_estate_taxes,
                mortgage_interest=personal_mortgage_interest,
            )
    else:
        # Schedule A was created from property tax / config; ensure 1098 mortgage interest is in
        if personal_mortgage_interest > 0 and schedule_a_data.mortgage_interest == 0:
            schedule_a_data.mortgage_interest = personal_mortgage_interest

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
    # Step 4: State Tax (CA Form 540, NY IT-201, etc.; no-tax states return None)
    # ---------------------------------------------------------------
    state_of_residence = getattr(taxpayer, "state_of_residence", "CA") or "CA"
    tax_return.state_of_residence = state_of_residence
    federal_agi = tax_return.federal_calculation.adjusted_gross_income
    state_credits = TaxCredits()

    state_estimated = sum(
        p.amount for p in tax_return.estimated_payments
        if (p.jurisdiction == "california" and state_of_residence == "CA")
        or (p.jurisdiction in ("new_york", "ny") and state_of_residence == "NY")
        or (p.jurisdiction in ("new_jersey", "nj") and state_of_residence == "NJ")
        or (p.jurisdiction in ("pennsylvania", "pa") and state_of_residence == "PA")
    )
    tax_return.state_calculation = calculate_state_tax(
        state_code=state_of_residence,
        filing_status=taxpayer.filing_status,
        tax_year=tax_year,
        income=income,
        deductions=deductions,
        credits=state_credits,
        state_withheld=tax_return.total_state_withheld,
        num_exemptions=taxpayer.num_exemptions,
        is_renter=taxpayer.is_renter,
        schedule_a_data=schedule_a_data,
        schedule_e_summary=schedule_e_summary,
        estimated_payments=state_estimated,
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
        Dependent(name=d.name, age=d.age, relationship=d.relationship, ssn=d.ssn)
        for d in config.dependents
    ]
    return TaxpayerInfo(
        name=config.taxpayer_name,
        ssn=config.taxpayer_ssn,
        spouse_ssn=config.spouse_ssn,
        spouse_name=config.spouse_name,
        filing_status=filing_status,
        age=config.age,
        state_of_residence=getattr(config, "state_of_residence", "CA"),
        is_ca_resident=config.is_ca_resident,
        is_renter=config.is_renter,
        address_line1=getattr(config, "address_line1", ""),
        address_line2=getattr(config, "address_line2", ""),
        date_of_birth=getattr(config, "date_of_birth", None) or None,
        spouse_dob=getattr(config, "spouse_dob", None) or None,
        county=getattr(config, "county", ""),
        dependents=deps,
    )


def process_tax_documents(
    local_files: Optional[list] = None,
    local_folder: Optional[str] = None,
    config: Optional[TaxProfileConfig] = None,
) -> TaxReturn:
    """Process tax documents from local files or folder."""
    parser = DocumentParser()

    # Build taxpayer from config or defaults
    if config:
        taxpayer = _build_taxpayer_from_config(config)
        tax_year = config.tax_year
    else:
        taxpayer = TaxpayerInfo(name="Taxpayer", filing_status=FilingStatus.SINGLE)
        tax_year = 2025

    extractor = TaxDataExtractor(tax_year=tax_year)

    income = TaxableIncome()
    tax_return = TaxReturn(taxpayer=taxpayer, income=income, tax_year=tax_year)

    parsed_docs = []
    category_hints = {}  # file path -> category from folder scan

    # Determine the document folder
    doc_folder = local_folder or (config.document_folder if config else None)

    if doc_folder:
        # Print inventory and collect all files for parsing.
        # Form type is determined entirely from document content —
        # no folder or filename hints are used.
        summary = scan_and_categorize_folder(doc_folder)

        all_files = []
        for files in summary.values():
            for f in files:
                all_files.append(f.path)

        if all_files:
            print(f"\nProcessing {len(all_files)} document(s) through OCR/parsing...")
            parsed_docs = parser.parse_multiple(all_files)
        else:
            print("\nNo documents found.")
    elif local_files:
        print("\nProcessing local files...")
        parsed_docs = parser.parse_multiple(local_files)

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
            elif result.form_type == '1099-MISC':
                form = result.data
                tax_return.form_1099_misc.append(form)
                income.other_income += form.other_income
            elif result.form_type == '1099-NEC':
                form = result.data
                tax_return.form_1099_nec.append(form)
                income.self_employment_income += form.nonemployee_compensation
            elif result.form_type == '1099-B':
                form = result.data
                tax_return.form_1099_b.append(form)
                if form.is_short_term:
                    income.short_term_capital_gains += form.gain_loss
                else:
                    income.long_term_capital_gains += form.gain_loss
                income.capital_gains += form.gain_loss
            elif result.form_type == '1099-R':
                form = result.data
                tax_return.form_1099_r.append(form)
                # Non-taxable distribution codes:
                #   G = direct rollover to another plan
                #   H = direct rollover from designated Roth account
                #   Q = qualified Roth IRA distribution (5-yr rule + age 59.5)
                dist_code = (form.distribution_code or "").strip().upper()
                non_taxable_codes = {"G", "H", "Q"}
                if dist_code not in non_taxable_codes:
                    income.retirement_income += form.taxable_amount
            elif result.form_type == 'Misc Deduction':
                form = result.data
                if not hasattr(tax_return, '_misc_deductions'):
                    tax_return._misc_deductions = []
                tax_return._misc_deductions.append(form)
            elif result.form_type == 'Schedule E':
                rental = result.data  # RentalProperty (partial: repairs, mgmt fees)
                if not hasattr(tax_return, '_extracted_rentals'):
                    tax_return._extracted_rentals = []
                tax_return._extracted_rentals.append(rental)
            elif result.form_type == '1098':
                form = result.data
                # Tag rental 1098s by matching the extracted property address (Box 8),
                # file path, and full document text against rental property addresses
                # from config.rental_properties.
                if config and config.rental_properties:
                    rental_kws = [
                        w.lower()
                        for rp in config.rental_properties
                        for w in (rp.address or "").split()
                        if len(w) > 4
                    ]
                    addr = (form.property_address or "").lower()
                    path_lower = (result.source_file or "").lower()
                    doc_text = (result.source_text or "").lower()
                    if any(kw in addr or kw in path_lower or kw in doc_text
                           for kw in rental_kws):
                        form.is_rental = True
                tax_return.form_1098.append(form)
            elif result.form_type == '1099-G':
                form = result.data
                tax_return.form_1099_g.append(form)
                income.other_income += form.unemployment_compensation
                if form.state_tax_refund > 0:
                    income.other_income += form.state_tax_refund
            elif result.form_type == '1098-T':
                tax_return.form_1098_t.append(result.data)
            elif result.form_type == 'Estimated Payment':
                tax_return.estimated_payments.append(result.data)
            elif result.form_type == 'Vehicle Registration':
                if tax_return.schedule_a_data is None:
                    tax_return.schedule_a_data = ScheduleAData()
                tax_return.schedule_a_data.vehicle_registrations.append(result.data)
            elif result.form_type == 'Property Tax':
                rec = result.data
                # Only include payments for current tax year (or undated)
                if rec.payment_date is not None and rec.payment_date.year != tax_return.tax_year:
                    continue
                if not hasattr(tax_return, '_property_tax_receipts'):
                    tax_return._property_tax_receipts = []
                tax_return._property_tax_receipts.append(rec)
            elif result.form_type == 'FSA':
                dc = result.data
                if tax_return.dependent_care is None:
                    tax_return.dependent_care = DependentCareFSA(
                        amount_paid=dc.amount_paid,
                        fsa_contribution=dc.fsa_contribution,
                    )
                else:
                    tax_return.dependent_care.amount_paid += dc.amount_paid
                    tax_return.dependent_care.fsa_contribution += dc.fsa_contribution
            elif result.form_type == 'Charitable Contribution':
                if tax_return.schedule_a_data is None:
                    tax_return.schedule_a_data = ScheduleAData()
                tax_return.schedule_a_data.cash_contributions += result.data.amount
            elif result.form_type == 'Home Insurance':
                from src.data_extractor import HomeInsuranceRecord
                if isinstance(result.data, HomeInsuranceRecord) and result.data.annual_premium > 0:
                    if not hasattr(tax_return, '_insurance_records'):
                        tax_return._insurance_records = []
                    tax_return._insurance_records.append(result.data)

    # Resolve property tax receipts: split into primary (Schedule A) vs rental (Schedule E).
    # Build rental address keywords from config for content-based matching.
    rental_addr_keywords = []
    if config:
        for rp in (config.rental_properties or []):
            # Add words >4 chars from the rental address (e.g. "hiawatha", "sunnyvale")
            rental_addr_keywords.extend(
                w.lower() for w in (rp.address or "").split() if len(w) > 4
            )

    def _is_rental_parcel(address: str) -> bool:
        addr_lower = (address or "").lower()
        return bool(rental_addr_keywords and any(kw in addr_lower for kw in rental_addr_keywords))

    ptax_receipts = getattr(tax_return, '_property_tax_receipts', [])
    if ptax_receipts:
        primary_apn = (config.primary_home_apn if config else "").strip()
        all_parcels = []  # PropertyTaxParcel list
        for rec in ptax_receipts:
            if rec.parcels:
                all_parcels.extend(rec.parcels)
            elif rec.address or rec.is_rental:
                # Single-property receipt (payment history format)
                from src.data_extractor import PropertyTaxParcel
                all_parcels.append(PropertyTaxParcel(
                    apn=getattr(rec, 'parcels', [{}])[0].apn if rec.parcels else "",
                    address=rec.address,
                    amount=rec.amount,
                ))
            else:
                # Simple receipt, no parcel info — treat as primary
                if tax_return.schedule_a_data is None:
                    tax_return.schedule_a_data = ScheduleAData()
                tax_return.schedule_a_data.real_estate_taxes += rec.amount

        if len(all_parcels) > 1 and primary_apn:
            # User configured a primary home APN — split accordingly
            if tax_return.schedule_a_data is None:
                tax_return.schedule_a_data = ScheduleAData()
            if not hasattr(tax_return, '_extracted_rental_property_tax'):
                tax_return._extracted_rental_property_tax = 0.0
            for p in all_parcels:
                if p.apn == primary_apn or p.address == primary_apn:
                    tax_return.schedule_a_data.real_estate_taxes += p.amount
                else:
                    tax_return._extracted_rental_property_tax += p.amount
        elif len(all_parcels) >= 1:
            # Route each parcel by matching against known rental addresses from config.
            if tax_return.schedule_a_data is None:
                tax_return.schedule_a_data = ScheduleAData()
            if not hasattr(tax_return, '_extracted_rental_property_tax'):
                tax_return._extracted_rental_property_tax = 0.0
            for p in all_parcels:
                if _is_rental_parcel(p.address):
                    tax_return._extracted_rental_property_tax += p.amount
                else:
                    tax_return.schedule_a_data.real_estate_taxes += p.amount

    # US Treasury interest: auto-extracted from 1099-INT/DIV Box 3.
    # Config value is used as a fallback override if auto-extraction finds nothing.
    auto_treasury = sum(f.us_treasury_interest for f in tax_return.form_1099_int) + \
                    sum(f.us_treasury_interest for f in tax_return.form_1099_div)
    if auto_treasury > 0:
        if config and config.us_treasury_interest > 0 and abs(auto_treasury - config.us_treasury_interest) > 1.0:
            print(f"\n  NOTE: Auto-extracted US Treasury interest ${auto_treasury:,.2f} "
                  f"differs from config ${config.us_treasury_interest:,.2f}. Using auto-extracted value.")
    elif config and config.us_treasury_interest > 0:
        # Fallback: use config value if auto-extraction found nothing
        treasury_marker = Form1099Int(
            payer_name="US Treasury (config override)",
            interest_income=0.0,
            us_treasury_interest=config.us_treasury_interest,
        )
        tax_return.form_1099_int.append(treasury_marker)

    # Apply capital loss carryover from prior year (Schedule D)
    # If ST/LT split is provided, apply each to respective gain type first,
    # then combine for the $3K net loss cap. Otherwise fall back to single total.
    if config and (config.short_term_loss_carryover > 0 or config.long_term_loss_carryover > 0):
        st_carry = config.short_term_loss_carryover
        lt_carry = config.long_term_loss_carryover
        carryover = st_carry + lt_carry

        # Apply ST carryover to ST gains, LT carryover to LT gains
        net_st = income.short_term_capital_gains - st_carry
        net_lt = income.long_term_capital_gains - lt_carry
        net_total = net_st + net_lt

        deductible_loss = 0.0
        if net_total >= 0:
            remaining_carryover = 0.0
        else:
            cap = 1_500 if taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY else 3_000
            deductible_loss = min(cap, abs(net_total))
            remaining_carryover = abs(net_total) - deductible_loss
            net_total = -deductible_loss

        income.short_term_capital_gains = net_st
        income.long_term_capital_gains = net_lt
        income.capital_gains = net_total
        tax_return._capital_loss_carryover_applied = carryover
        tax_return._capital_loss_carryover_remaining = round(remaining_carryover, 2)
        tax_return._capital_loss_deductible_used = round(deductible_loss, 2)

    elif config and config.capital_loss_carryover > 0:
        carryover = config.capital_loss_carryover
        current_gains = income.capital_gains  # Before carryover
        net = current_gains - carryover
        deductible_loss = 0.0
        if net >= 0:
            # Carryover fully absorbed by gains
            income.capital_gains = net
            remaining_carryover = 0.0
        else:
            # Net loss — cap deductible loss at $3K ($1.5K MFS)
            cap = 1_500 if taxpayer.filing_status == FilingStatus.MARRIED_FILING_SEPARATELY else 3_000
            deductible_loss = min(cap, abs(net))
            income.capital_gains = -deductible_loss
            remaining_carryover = abs(net) - deductible_loss
        # Store for report (starting carryover, amount used this year, remaining)
        tax_return._capital_loss_carryover_applied = carryover
        tax_return._capital_loss_carryover_remaining = round(remaining_carryover, 2)
        tax_return._capital_loss_deductible_used = round(deductible_loss, 2)

    # Dividend overrides: if config has values, replace extracted (for when extraction undercounts)
    if config and config.qualified_dividends > 0:
        income.qualified_dividends = config.qualified_dividends
    if config and config.ordinary_dividends > 0:
        income.dividend_income = config.ordinary_dividends

    # Other income: auto-extracted from 1099-MISC forms + 1099-G.
    # Config value is ADDED on top of auto-extracted (for forms that failed OCR).
    if config and config.other_income != 0:
        income.other_income += config.other_income

    # Apply estimated tax payments from config (before schedule_a_data creation,
    # because CA estimated payments count towards state_income_tax_paid for SALT).
    # Config overrides extraction: when set, replace any extracted federal/CA estimated
    # payments so we don't double-count (config 100k + extracted 100k = 200k).
    if config and config.federal_estimated_payments > 0:
        tax_return.estimated_payments = [
            p for p in tax_return.estimated_payments if p.jurisdiction != "federal"
        ]
        tax_return.estimated_payments.append(EstimatedTaxPayment(
            amount=config.federal_estimated_payments,
            period="Total",
            jurisdiction="federal",
        ))
    if config and config.ca_estimated_payments > 0:
        tax_return.estimated_payments = [
            p for p in tax_return.estimated_payments if p.jurisdiction != "california"
        ]
        tax_return.estimated_payments.append(EstimatedTaxPayment(
            amount=config.ca_estimated_payments,
            period="Total",
            jurisdiction="california",
        ))

    # Apply prior-year PAL carryover from config
    if config and config.pal_carryover > 0:
        tax_return.prior_pal_carryover = config.pal_carryover

    # Apply federal withholding adjustment from config (optional OCR correction override)
    if config and config.federal_withheld_adjustment != 0:
        tax_return.federal_withheld_adjustment = config.federal_withheld_adjustment
        print(f"\n  WARNING: Using federal_withheld_adjustment = ${config.federal_withheld_adjustment:,.2f} "
              f"from config. This overrides auto-extracted withholding. "
              f"Remove this config field once W-2 OCR extraction is verified accurate.")

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

    # CA-only miscellaneous deductions: auto-extracted from Misc Deduction docs.
    # Config value is used as fallback override.
    auto_misc = sum(d.amount for d in getattr(tax_return, '_misc_deductions', []))
    if auto_misc > 0 and tax_return.schedule_a_data:
        tax_return.schedule_a_data.ca_misc_deductions = auto_misc
        if config and config.ca_misc_deductions > 0 and abs(auto_misc - config.ca_misc_deductions) > 1.0:
            print(f"\n  NOTE: Auto-extracted CA misc deductions ${auto_misc:,.2f} "
                  f"differs from config ${config.ca_misc_deductions:,.2f}. Using auto-extracted value.")
    elif config and config.ca_misc_deductions > 0 and tax_return.schedule_a_data:
        tax_return.schedule_a_data.ca_misc_deductions = config.ca_misc_deductions

    # Build rental properties from config + auto-extracted PM data
    if config and config.rental_properties:
        from datetime import datetime as _dt
        extracted_rentals = getattr(tax_return, '_extracted_rentals', [])

        for rp_cfg in config.rental_properties:
            purchase_date_val = None
            if rp_cfg.purchase_date:
                try:
                    purchase_date_val = _dt.strptime(rp_cfg.purchase_date, "%Y-%m-%d").date()
                except ValueError:
                    pass

            rental = RentalProperty(
                address=rp_cfg.address,
                property_type=rp_cfg.property_type,
                purchase_price=rp_cfg.purchase_price,
                purchase_date=purchase_date_val,
                land_value=rp_cfg.land_value,
                rental_income=rp_cfg.rental_income,
                insurance=rp_cfg.insurance,
                property_tax=rp_cfg.property_tax,
                other_expenses=rp_cfg.other_expenses,
                days_rented=rp_cfg.days_rented,
                personal_use_days=rp_cfg.personal_use_days,
            )

            # Merge auto-extracted data (repairs, management fees) from PM statements
            # Match by address keyword overlap
            addr_lower = rp_cfg.address.lower()
            for ext in extracted_rentals:
                ext_addr = ext.address.lower()
                # Match if any significant word from the extracted property name
                # appears in the config address (e.g. "Hiawatha" in both)
                ext_words = [w for w in ext_addr.split() if len(w) > 3]
                if any(w in addr_lower for w in ext_words) or not ext_addr:
                    if ext.repairs > 0:
                        rental.repairs += ext.repairs
                    if ext.management_fees > 0:
                        rental.management_fees += ext.management_fees

            # Add rental 1098 mortgage interest
            for f1098 in tax_return.form_1098:
                if f1098.is_rental:
                    rental.mortgage_interest += f1098.mortgage_interest

            tax_return.rental_properties.append(rental)

        # Apply extracted property tax from receipts to first rental property.
        # Extracted value replaces the config value (docs take priority over config estimates).
        extracted_rental_ptax = getattr(tax_return, '_extracted_rental_property_tax', 0.0)
        if extracted_rental_ptax > 0 and tax_return.rental_properties:
            tax_return.rental_properties[0].property_tax = extracted_rental_ptax

        # Apply extracted insurance premiums to matching rental properties.
        # Only assign to rental if the insurance doc matches a rental address
        # (by address field or rental keywords in source text). Otherwise skip
        # (personal home insurance is not a deductible Schedule E expense).
        insurance_records = getattr(tax_return, '_insurance_records', [])
        for ins in insurance_records:
            ins_addr = ins.property_address.lower()
            ins_text = (ins.source_text or "").lower()
            matched = False
            for rp in tax_return.rental_properties:
                rp_addr = rp.address.lower()
                ins_words = [w for w in ins_addr.split() if len(w) > 3]
                rp_words = [w for w in rp_addr.split() if len(w) > 3]
                # Match by address keyword overlap or rental property address words in source text
                if (ins_words and any(w in rp_addr for w in ins_words)) or \
                   any(w in ins_text for w in rp_words):
                    rp.insurance += ins.annual_premium
                    matched = True
                    break

    # Override Schedule A real estate taxes from config (e.g. correct 2025 primary residence total)
    if config and config.primary_property_tax > 0:
        if tax_return.schedule_a_data is None:
            tax_return.schedule_a_data = ScheduleAData()
        tax_return.schedule_a_data.real_estate_taxes = config.primary_property_tax

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
    print(f"  1099-MISC forms: {len(tax_return.form_1099_misc)}")
    print(f"  1099-NEC forms:  {len(tax_return.form_1099_nec)}")
    print(f"  1099-B forms:    {len(tax_return.form_1099_b)}")
    print(f"  1099-R forms:    {len(tax_return.form_1099_r)}")
    print(f"  1098 forms:      {len(tax_return.form_1098)}"
          f" ({sum(1 for f in tax_return.form_1098 if not f.is_rental)} personal,"
          f" {sum(1 for f in tax_return.form_1098 if f.is_rental)} rental)")
    for i, f1098 in enumerate(tax_return.form_1098, 1):
        tag = "rental" if f1098.is_rental else "personal"
        print(f"    1098 #{i}: {f1098.lender_name!r}  interest={fmt(f1098.mortgage_interest)}  [{tag}]")

    # Per-form interest detail for debugging
    if tax_return.form_1099_int:
        print(f"\n  1099-INT detail:")
        for i, fi in enumerate(tax_return.form_1099_int, 1):
            print(f"    #{i}: {fi.payer_name!r}  box1={fmt(fi.interest_income)}  box3={fmt(fi.us_treasury_interest)}")

    # Per-form dividend detail for debugging over/under-counting
    if tax_return.form_1099_div:
        print(f"\n  1099-DIV detail:")
        for i, fd in enumerate(tax_return.form_1099_div, 1):
            print(f"    #{i}: {fd.payer_name!r}  ord={fmt(fd.ordinary_dividends)}  qual={fmt(fd.qualified_dividends)}  capgain={fmt(fd.capital_gain_distributions)}")

    print(f"\n  Wages:                     {fmt(inc.wages)}")
    print(f"  Interest income:           {fmt(inc.interest_income)}")
    print(f"  Ordinary dividends:        {fmt(inc.dividend_income)}")
    print(f"  Qualified dividends:       {fmt(inc.qualified_dividends)}")
    print(f"  Capital gains:             {fmt(inc.capital_gains)}")
    if inc.short_term_capital_gains != 0 or inc.long_term_capital_gains != 0:
        print(f"    Short-term:              {fmt(inc.short_term_capital_gains)}")
        print(f"    Long-term:               {fmt(inc.long_term_capital_gains)}")
    print(f"  Other income:              {fmt(inc.other_income)}")
    print(f"  Self-employment:           {fmt(inc.self_employment_income)}")
    print(f"  Retirement:                {fmt(inc.retirement_income)}")
    print(f"  US Treasury interest:      {fmt(tax_return.total_us_treasury_interest)}")

    pers_int = tax_return.total_personal_mortgage_interest
    rent_int = tax_return.total_rental_mortgage_interest
    # "Personal property taxes" in summary = 1098 Box 10 only (personal 1098s). Schedule A uses 1098 + receipts, or config override.
    pers_prop_tax_1098 = sum(f.property_taxes for f in tax_return.form_1098 if not f.is_rental)
    print(f"\n  Personal mortgage interest:{fmt(pers_int)}")
    print(f"  Rental mortgage interest:  {fmt(rent_int)}")
    if tax_return.form_1098 and pers_int == 0 and rent_int > 0:
        print("  *** NOTE: All 1098s are tagged [rental]. If the primary residence has a 1098, ensure its property address differs from addresses in rental_properties.")
    elif tax_return.form_1098 and pers_int == 0:
        print("  *** NOTE: Personal mortgage interest is $0. Check 1098 extraction (amount parsed?) and verify primary residence address does not match any rental_properties address.")
    print(f"  1098 Box 10 (personal) property taxes: {fmt(pers_prop_tax_1098)}")
    if tax_return.schedule_a_data is not None:
        print(f"  Schedule A real estate taxes (used for SALT): {fmt(tax_return.schedule_a_data.real_estate_taxes)}")
    extracted_rental_ptax = getattr(tax_return, '_extracted_rental_property_tax', 0.0)
    if extracted_rental_ptax != 0:
        print(f"  Extracted rental property tax (2025 receipts): {fmt(extracted_rental_ptax)}")
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

    # Capital loss carryover
    if hasattr(tax_return, '_capital_loss_carryover_applied') and tax_return._capital_loss_carryover_applied > 0:
        print(f"\n  Capital loss carryover:     {fmt(tax_return._capital_loss_carryover_applied)}")
        print(f"  Remaining carryover:       {fmt(tax_return._capital_loss_carryover_remaining)}")

    # Rental property summary
    if tax_return.rental_properties:
        print(f"\n  Rental properties:         {len(tax_return.rental_properties)}")
        for rp in tax_return.rental_properties:
            print(f"    {rp.address}:")
            print(f"      Gross rent:    {fmt(rp.rental_income)}")
            print(f"      Repairs:       {fmt(rp.repairs)}")
            print(f"      Mgmt fees:     {fmt(rp.management_fees)}")
            print(f"      Insurance:     {fmt(rp.insurance)}")
            print(f"      Property tax:  {fmt(rp.property_tax)}")
            print(f"      Other expense: {fmt(rp.other_expenses)}")
            print(f"      Mortgage int:  {fmt(rp.mortgage_interest)}")
            print(f"      Depreciation:  {'N/A (missing purchase data)' if rp.purchase_price == 0 else fmt(rp.depreciable_basis / 27.5)}")

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
        name="John Doe",
        spouse_name="Jane Doe",
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        age=42,
        state_of_residence="CA",
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
        "--pdf", action="store_true",
        help="Generate filled PDF tax forms (requires templates in pdf_templates/)"
    )
    parser.add_argument(
        "--pdf-output",
        default=None,
        help="Output directory for PDF forms (default: output/<year>/)"
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

    print("\n  ------------------------------------------------------------")
    print("  PRIVACY NOTICE")
    print("  ------------------------------------------------------------")
    print("  All processing runs 100% locally on your machine.")
    print("  No documents, OCR results, or tax data are sent anywhere.")
    print("  For extra assurance, you may disconnect from the internet")
    print("  before running this command.")
    print("  ------------------------------------------------------------\n")

    if args.demo:
        tax_return = run_demo()
        if args.pdf:
            from .form_filler import generate_all_forms
            generate_all_forms(tax_return, output_dir=args.pdf_output or "")
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

    if args.pdf:
        from .form_filler import generate_all_forms
        generate_all_forms(tax_return, output_dir=args.pdf_output or "")


if __name__ == "__main__":
    main()
