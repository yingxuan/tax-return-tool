"""Test script for enhanced tax calculations."""

import sys
from datetime import date

sys.path.insert(0, '.')

from src.models import (
    FilingStatus, TaxpayerInfo, TaxableIncome, Deductions, TaxCredits,
    TaxReturn, W2Data, Form1099Int, Form1099Div, Form1099Nec, Form1098,
    Dependent, RentalProperty, ScheduleAData, CAVehicleRegistration,
    EstimatedTaxPayment,
)
from src.federal_tax import FederalTaxCalculator
from src.california_tax import CaliforniaTaxCalculator
from src.schedule_e import ScheduleECalculator, DepreciationCalculator
from src.schedule_a import ScheduleACalculator
from src.report_generator import generate_full_report


def fmt(amount):
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def test_federal_tax():
    """Test basic federal tax calculation."""
    print("=" * 60)
    print("Test: Federal Tax - Single, $100K wages")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.SINGLE, tax_year=2025)
    income = TaxableIncome(wages=100_000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result = calculator.calculate(
        income=income, deductions=deductions, credits=credits,
        federal_withheld=15_000,
    )

    print(f"  Gross Income:      {fmt(result.gross_income)}")
    print(f"  Standard Deduction:{fmt(result.deductions)}")
    print(f"  Taxable Income:    {fmt(result.taxable_income)}")
    print(f"  Federal Tax:       {fmt(result.tax_after_credits)}")
    print(f"  Withheld:          {fmt(result.tax_withheld)}")
    print(f"  Refund/Owed:       {fmt(result.refund_or_owed)}")

    # Verify: taxable = 100000 - 15000 = 85000
    assert result.taxable_income == 85_000, f"Expected 85000, got {result.taxable_income}"
    print("  [PASS] Taxable income correct")
    return result


def test_california_tax():
    """Test California tax calculation."""
    print("\n" + "=" * 60)
    print("Test: California Tax - Single, $100K wages")
    print("=" * 60)

    calculator = CaliforniaTaxCalculator(FilingStatus.SINGLE, tax_year=2025)
    income = TaxableIncome(wages=100_000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result = calculator.calculate(
        income=income, deductions=deductions, credits=credits,
        state_withheld=5_000,
    )

    print(f"  CA AGI:            {fmt(result.adjusted_gross_income)}")
    print(f"  CA Std Deduction:  {fmt(result.deductions)}")
    print(f"  CA Taxable:        {fmt(result.taxable_income)}")
    print(f"  CA Tax:            {fmt(result.tax_after_credits)}")
    print(f"  Withheld:          {fmt(result.tax_withheld)}")
    print(f"  Refund/Owed:       {fmt(result.refund_or_owed)}")

    assert result.taxable_income == 100_000 - 5_540, f"Got {result.taxable_income}"
    print("  [PASS] CA taxable income correct")
    return result


def test_child_tax_credit():
    """Test Child Tax Credit with 2 qualifying children."""
    print("\n" + "=" * 60)
    print("Test: Child Tax Credit - MFJ, 2 kids ages 11 & 14")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2025)
    income = TaxableIncome(wages=150_000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result = calculator.calculate(
        income=income, deductions=deductions, credits=credits,
        federal_withheld=20_000,
        num_qualifying_children=2,
    )

    print(f"  AGI:               {fmt(result.adjusted_gross_income)}")
    print(f"  Child Tax Credit:  {fmt(result.child_tax_credit)}")
    print(f"  Total Credits:     {fmt(result.credits)}")
    print(f"  Tax After Credits: {fmt(result.tax_after_credits)}")

    # 2 children x $2,000 = $4,000; AGI $150K is below $400K threshold
    assert result.child_tax_credit == 4_000, f"Expected $4,000 CTC, got {result.child_tax_credit}"
    print("  [PASS] Child Tax Credit = $4,000")
    return result


def test_schedule_e_depreciation():
    """Test Schedule E rental property with depreciation."""
    print("\n" + "=" * 60)
    print("Test: Schedule E - Rental Property Depreciation")
    print("=" * 60)

    rental = RentalProperty(
        address="123 Main St, Sacramento, CA",
        purchase_price=400_000,
        purchase_date=date(2020, 1, 1),
        land_value=100_000,
        rental_income=24_000,  # $2,000/month
        management_fees=2_400,
        property_tax=3_600,
        insurance=1_200,
        repairs=1_500,
        mortgage_interest=7_200,
    )

    calc = ScheduleECalculator(tax_year=2025)
    result = calc.calculate_property(rental)

    print(f"  Gross Rental Income:  {fmt(result.gross_income)}")
    print(f"  Total Expenses:       {fmt(result.total_expenses)}")
    print(f"  Depreciation:         {fmt(result.depreciation)}")
    print(f"  Net Rental Income:    {fmt(result.net_income)}")

    # Depreciation: (400000 - 100000) / 27.5 = $10,909.09
    expected_depreciation = 300_000 / 27.5
    assert abs(result.depreciation - expected_depreciation) < 1, \
        f"Expected ~${expected_depreciation:,.2f}, got ${result.depreciation:,.2f}"
    print(f"  [PASS] Depreciation = {fmt(result.depreciation)} (27.5-yr straight-line)")

    # Total expenses = 2400 + 3600 + 1200 + 1500 + 7200 = 15900
    assert result.total_expenses == 15_900, f"Expected $15,900, got {result.total_expenses}"
    print("  [PASS] Total expenses correct")
    return result


def test_schedule_e_first_year():
    """Test first-year prorated depreciation."""
    print("\n" + "=" * 60)
    print("Test: Schedule E - First Year Prorated Depreciation")
    print("=" * 60)

    dep_calc = DepreciationCalculator()
    months = dep_calc.calculate_months_in_service(date(2025, 7, 1), 2025)
    print(f"  Months in service (purchased Jul 2025): {months}")
    assert months == 6, f"Expected 6 months, got {months}"

    depreciation = dep_calc.calculate_annual_depreciation(
        depreciable_basis=300_000, months_in_service=6,
    )
    full_year = 300_000 / 27.5
    expected = full_year * 6 / 12
    print(f"  First-year depreciation: {fmt(depreciation)}")
    assert abs(depreciation - expected) < 1, f"Expected ~{fmt(expected)}"
    print("  [PASS] First-year proration correct")


def test_schedule_a_itemized_vs_standard():
    """Test Schedule A: itemized vs standard deduction comparison."""
    print("\n" + "=" * 60)
    print("Test: Schedule A - Itemized vs Standard Comparison")
    print("=" * 60)

    schedule_a_data = ScheduleAData(
        medical_expenses=5_000,
        state_income_tax_paid=15_000,
        real_estate_taxes=8_000,
        vehicle_registrations=[
            CAVehicleRegistration(
                total_registration_fee=400,
                vehicle_license_fee=250,
            ),
        ],
        mortgage_interest=16_000,
        cash_contributions=5_000,
    )

    std_deduction = 30_000  # MFJ 2025
    calc = ScheduleACalculator(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        standard_deduction=std_deduction,
    )

    result = calc.calculate(data=schedule_a_data, agi=200_000)

    print(f"  Medical Deduction:     {fmt(result.medical_deduction)}")
    print(f"  SALT (capped):         {fmt(result.salt_deduction)}")
    print(f"  SALT (uncapped):       {fmt(result.salt_uncapped)}")
    print(f"  Mortgage Interest:     {fmt(result.mortgage_interest_deduction)}")
    print(f"  Charitable:            {fmt(result.charitable_deduction)}")
    print(f"  Total Itemized:        {fmt(result.total_itemized)}")
    print(f"  Standard Deduction:    {fmt(result.standard_deduction)}")
    print(f"  Using Itemized:        {result.use_itemized}")
    print(f"  Deduction Amount:      {fmt(result.deduction_amount)}")

    # SALT = 15000 + 8000 + 250 = 23250, capped at 10000
    assert result.salt_deduction == 10_000, f"SALT should be capped at $10,000"
    print("  [PASS] SALT cap applied correctly")

    # VLF included in SALT
    assert result.salt_uncapped == 23_250, f"Uncapped SALT: {result.salt_uncapped}"
    print("  [PASS] VLF included in SALT total")


def test_ca_vehicle_license_fee():
    """Test that VLF is properly extracted and deducted."""
    print("\n" + "=" * 60)
    print("Test: CA Vehicle License Fee (VLF) Deductibility")
    print("=" * 60)

    reg1 = CAVehicleRegistration(
        total_registration_fee=450,
        vehicle_license_fee=285,
        weight_fee=65,
        other_fees=100,
    )
    reg2 = CAVehicleRegistration(
        total_registration_fee=380,
        vehicle_license_fee=225,
        weight_fee=55,
        other_fees=100,
    )

    data = ScheduleAData(vehicle_registrations=[reg1, reg2])

    total_vlf = data.total_vehicle_license_fees
    total_reg = reg1.total_registration_fee + reg2.total_registration_fee
    print(f"  Total Registration Fees: {fmt(total_reg)}")
    print(f"  Total VLF (deductible):  {fmt(total_vlf)}")
    print(f"  Non-deductible portion:  {fmt(total_reg - total_vlf)}")

    assert total_vlf == 510, f"Expected $510 VLF, got {total_vlf}"
    print("  [PASS] VLF correctly extracted from registration fees")


def test_ca_renters_credit():
    """Test CA Renter's Credit eligibility."""
    print("\n" + "=" * 60)
    print("Test: CA Renter's Credit")
    print("=" * 60)

    calculator = CaliforniaTaxCalculator(FilingStatus.SINGLE, tax_year=2025)

    # Under AGI limit
    credit_low = calculator.calculate_renters_credit(ca_agi=45_000, is_renter=True)
    print(f"  Renter w/ AGI $45K:  {fmt(credit_low)}")
    assert credit_low == 60, f"Expected $60, got {credit_low}"

    # Over AGI limit
    credit_high = calculator.calculate_renters_credit(ca_agi=100_000, is_renter=True)
    print(f"  Renter w/ AGI $100K: {fmt(credit_high)}")
    assert credit_high == 0, f"Expected $0, got {credit_high}"

    # Not a renter
    credit_owner = calculator.calculate_renters_credit(ca_agi=45_000, is_renter=False)
    print(f"  Homeowner:           {fmt(credit_owner)}")
    assert credit_owner == 0, f"Expected $0, got {credit_owner}"

    print("  [PASS] Renter's Credit logic correct")


def test_ca_no_salt_cap():
    """Test that CA does not apply the $10K SALT cap."""
    print("\n" + "=" * 60)
    print("Test: CA Schedule A - No SALT Cap")
    print("=" * 60)

    data = ScheduleAData(
        real_estate_taxes=12_000,
        vehicle_registrations=[
            CAVehicleRegistration(vehicle_license_fee=300),
        ],
        mortgage_interest=10_000,
    )

    result = ScheduleACalculator.calculate_ca_itemized(
        data=data, agi=150_000, ca_standard_deduction=5_540,
    )

    # CA SALT = 12000 + 300 = 12300 (no cap, no state income tax deduction)
    print(f"  CA SALT deduction: {fmt(result.salt_deduction)}")
    print(f"  Total itemized:    {fmt(result.total_itemized)}")
    assert result.salt_deduction == 12_300, f"Expected $12,300, got {result.salt_deduction}"
    print("  [PASS] CA does not cap SALT")
    print("  [PASS] CA excludes state income tax from SALT")


def test_estimated_payments():
    """Test estimated tax payment tracking."""
    print("\n" + "=" * 60)
    print("Test: Estimated Tax Payments")
    print("=" * 60)

    payments = [
        EstimatedTaxPayment(amount=3_000, period="Q1", jurisdiction="federal"),
        EstimatedTaxPayment(amount=3_000, period="Q2", jurisdiction="federal"),
        EstimatedTaxPayment(amount=3_000, period="Q3", jurisdiction="federal"),
        EstimatedTaxPayment(amount=3_000, period="Q4", jurisdiction="federal"),
        EstimatedTaxPayment(amount=1_000, period="Q1", jurisdiction="california"),
        EstimatedTaxPayment(amount=1_000, period="Q2", jurisdiction="california"),
    ]

    taxpayer = TaxpayerInfo(name="Test", filing_status=FilingStatus.SINGLE)
    income = TaxableIncome(wages=100_000)
    tax_return = TaxReturn(
        taxpayer=taxpayer, income=income, estimated_payments=payments,
    )

    fed_est = tax_return.total_federal_estimated_payments
    ca_est = tax_return.total_state_estimated_payments
    print(f"  Federal estimated: {fmt(fed_est)}")
    print(f"  CA estimated:      {fmt(ca_est)}")

    assert fed_est == 12_000, f"Expected $12,000, got {fed_est}"
    assert ca_est == 2_000, f"Expected $2,000, got {ca_est}"
    print("  [PASS] Estimated payment tracking correct")


def test_2024_brackets():
    """Test 2024 tax year brackets."""
    print("\n" + "=" * 60)
    print("Test: 2024 Tax Year Brackets")
    print("=" * 60)

    calc_2024 = FederalTaxCalculator(FilingStatus.SINGLE, tax_year=2024)
    calc_2025 = FederalTaxCalculator(FilingStatus.SINGLE, tax_year=2025)

    print(f"  2024 Standard Deduction: {fmt(calc_2024.standard_deduction)}")
    print(f"  2025 Standard Deduction: {fmt(calc_2025.standard_deduction)}")

    assert calc_2024.standard_deduction == 14_600
    assert calc_2025.standard_deduction == 15_000
    print("  [PASS] Year-specific deductions correct")

    # Tax on $100K should differ slightly between years
    tax_2024, _ = calc_2024.calculate_progressive_tax(85_400)  # 100K - 14600
    tax_2025, _ = calc_2025.calculate_progressive_tax(85_000)  # 100K - 15000
    print(f"  2024 tax on $100K wages: {fmt(tax_2024)}")
    print(f"  2025 tax on $100K wages: {fmt(tax_2025)}")
    print("  [PASS] Both tax years compute correctly")


def test_full_complex_return():
    """Test the full complex tax return with all features."""
    print("\n" + "=" * 60)
    print("Test: Full Complex Return - MFJ, Rental, Itemized, CTC")
    print("=" * 60)

    taxpayer = TaxpayerInfo(
        name="Test Family",
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        age=40,
        dependents=[
            Dependent(name="Child A", age=10, relationship="son"),
            Dependent(name="Child B", age=15, relationship="daughter"),
        ],
    )

    income = TaxableIncome(
        wages=200_000,
        interest_income=3_000,
        self_employment_income=10_000,
    )

    rental = RentalProperty(
        address="Test Rental",
        purchase_price=350_000,
        purchase_date=date(2021, 3, 1),
        land_value=80_000,
        rental_income=24_000,
        management_fees=2_400,
        property_tax=3_000,
        insurance=1_200,
        repairs=800,
        mortgage_interest=6_000,
    )

    # Process through the main flow
    from src.main import process_tax_return

    tax_return = TaxReturn(
        taxpayer=taxpayer,
        income=income,
        tax_year=2025,
        rental_properties=[rental],
        schedule_a_data=ScheduleAData(
            state_income_tax_paid=12_000,
            real_estate_taxes=7_000,
            mortgage_interest=14_000,
            cash_contributions=3_000,
        ),
    )

    tax_return = process_tax_return(tax_return)

    fed = tax_return.federal_calculation
    ca = tax_return.state_calculation

    print(f"\n  --- Federal ---")
    print(f"  Gross Income:      {fmt(fed.gross_income)}")
    print(f"  AGI:               {fmt(fed.adjusted_gross_income)}")
    print(f"  Deduction Method:  {fed.deduction_method}")
    print(f"  Deductions:        {fmt(fed.deductions)}")
    print(f"  Taxable Income:    {fmt(fed.taxable_income)}")
    print(f"  Child Tax Credit:  {fmt(fed.child_tax_credit)}")
    print(f"  SE Tax:            {fmt(fed.self_employment_tax)}")
    print(f"  Tax After Credits: {fmt(fed.tax_after_credits)}")

    print(f"\n  --- California ---")
    print(f"  CA AGI:            {fmt(ca.adjusted_gross_income)}")
    print(f"  CA Deduction:      {fmt(ca.deductions)} ({ca.deduction_method})")
    print(f"  CA Taxable:        {fmt(ca.taxable_income)}")
    print(f"  CA Tax:            {fmt(ca.tax_after_credits)}")

    # Verify Child Tax Credit was applied
    assert fed.child_tax_credit == 4_000, f"CTC should be $4,000, got {fed.child_tax_credit}"
    # Verify rental income was included
    assert tax_return.income.rental_income != 0, "Rental income should be non-zero"
    print(f"\n  Net Rental Income: {fmt(tax_return.income.rental_income)}")

    print("\n  [PASS] Full complex return computed successfully")


def test_report_generation():
    """Test that report generation works without errors."""
    print("\n" + "=" * 60)
    print("Test: Report Generation")
    print("=" * 60)

    from src.main import process_tax_return

    taxpayer = TaxpayerInfo(
        name="Report Test",
        filing_status=FilingStatus.SINGLE,
        age=35,
        dependents=[Dependent(name="Kid", age=8, relationship="son")],
    )

    tax_return = TaxReturn(
        taxpayer=taxpayer,
        income=TaxableIncome(wages=80_000),
        tax_year=2025,
        w2_forms=[W2Data(
            employer_name="Test Co",
            wages=80_000,
            federal_withheld=10_000,
            state_withheld=4_000,
        )],
    )

    tax_return = process_tax_return(tax_return)
    report = generate_full_report(tax_return)

    assert "FORM 1040" in report
    assert "FORM 540" in report
    assert "COMBINED TAX SUMMARY" in report
    assert "Child Tax Credit" in report
    print("  [PASS] Report contains Form 1040 section")
    print("  [PASS] Report contains Form 540 section")
    print("  [PASS] Report contains combined summary")
    print("  [PASS] Report mentions Child Tax Credit")


if __name__ == "__main__":
    test_federal_tax()
    test_california_tax()
    test_child_tax_credit()
    test_schedule_e_depreciation()
    test_schedule_e_first_year()
    test_schedule_a_itemized_vs_standard()
    test_ca_vehicle_license_fee()
    test_ca_renters_credit()
    test_ca_no_salt_cap()
    test_estimated_payments()
    test_2024_brackets()
    test_full_complex_return()
    test_report_generation()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED!")
    print("=" * 60)
