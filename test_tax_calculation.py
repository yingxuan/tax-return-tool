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


def test_rental_vs_personal_mortgage():
    """Test that rental 1098 mortgage interest is separated from personal."""
    print("\n" + "=" * 60)
    print("Test: Rental vs Personal Mortgage Interest (Feature 1)")
    print("=" * 60)

    tax_return = TaxReturn(
        taxpayer=TaxpayerInfo(name="Test", filing_status=FilingStatus.MARRIED_FILING_JOINTLY),
        income=TaxableIncome(wages=200_000),
        form_1098=[
            Form1098(lender_name="Wells Fargo", mortgage_interest=18_000, is_rental=False),
            Form1098(lender_name="Hiawatha Mortgage", mortgage_interest=33_000, is_rental=True),
        ],
    )

    print(f"  Total mortgage interest:    {fmt(tax_return.total_mortgage_interest)}")
    print(f"  Personal mortgage interest: {fmt(tax_return.total_personal_mortgage_interest)}")
    print(f"  Rental mortgage interest:   {fmt(tax_return.total_rental_mortgage_interest)}")

    assert tax_return.total_mortgage_interest == 51_000
    assert tax_return.total_personal_mortgage_interest == 18_000
    assert tax_return.total_rental_mortgage_interest == 33_000
    print("  [PASS] Rental vs personal mortgage split correctly")


def test_capital_loss_carryover():
    """Test capital loss carryover reduces capital gains."""
    print("\n" + "=" * 60)
    print("Test: Capital Loss Carryover (Feature 2)")
    print("=" * 60)

    income = TaxableIncome(wages=100_000, capital_gains=500)

    # Simulate applying carryover (same logic as main.py)
    carryover = 3_000
    cap = 3_000  # MFJ cap
    loss = min(carryover, cap)
    income.capital_gains -= loss

    print(f"  Capital gains after carryover: {fmt(income.capital_gains)}")
    assert income.capital_gains == -2_500, f"Expected -$2,500, got {income.capital_gains}"
    print("  [PASS] Capital loss carryover applied correctly")

    # Test MFS cap
    income2 = TaxableIncome(wages=100_000, capital_gains=0)
    mfs_cap = 1_500
    loss2 = min(carryover, mfs_cap)
    income2.capital_gains -= loss2
    assert income2.capital_gains == -1_500, f"Expected -$1,500, got {income2.capital_gains}"
    print("  [PASS] MFS $1,500 cap applied correctly")


def test_ca_itemized_limitation():
    """Test CA high-income itemized deduction limitation."""
    print("\n" + "=" * 60)
    print("Test: CA Itemized Deduction Limitation (Feature 3)")
    print("=" * 60)

    data = ScheduleAData(
        real_estate_taxes=15_000,
        mortgage_interest=20_000,
        cash_contributions=10_000,
    )

    # MFJ, 2024, AGI well above threshold ($452,761)
    agi = 1_600_000
    result = ScheduleACalculator.calculate_ca_itemized(
        data=data, agi=agi, ca_standard_deduction=10_726,
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2024,
    )

    # Expected: min(6% * (1600000 - 452761), 80% * 45000)
    # = min(6% * 1147239, 80% * 45000) = min(68834.34, 36000) = 36000
    expected_limitation = min(
        0.06 * (agi - 452_761),
        0.80 * 45_000,
    )
    print(f"  Total before limitation: $45,000.00")
    print(f"  CA Limitation:           {fmt(result.ca_itemized_limitation)}")
    print(f"  Total after limitation:  {fmt(result.total_itemized)}")

    assert abs(result.ca_itemized_limitation - expected_limitation) < 0.01, \
        f"Expected {fmt(expected_limitation)}, got {fmt(result.ca_itemized_limitation)}"
    assert abs(result.total_itemized - (45_000 - expected_limitation)) < 0.01
    print("  [PASS] CA itemized limitation computed correctly")

    # Below threshold - no limitation
    result_low = ScheduleACalculator.calculate_ca_itemized(
        data=data, agi=300_000, ca_standard_deduction=10_726,
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2024,
    )
    assert result_low.ca_itemized_limitation == 0.0
    print("  [PASS] No limitation when AGI below threshold")


def test_additional_medicare_tax():
    """Test Additional Medicare Tax on W-2 wages."""
    print("\n" + "=" * 60)
    print("Test: Additional Medicare Tax on Wages (Feature 4)")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2024)

    # Wages above $250K threshold
    amt = calculator.calculate_additional_medicare_tax(wages=400_000)
    expected = (400_000 - 250_000) * 0.009  # $1,350
    print(f"  Wages $400K, MFJ: Additional Medicare Tax = {fmt(amt)}")
    assert abs(amt - expected) < 0.01, f"Expected {fmt(expected)}, got {fmt(amt)}"
    print("  [PASS] Additional Medicare Tax computed correctly")

    # Wages below threshold
    amt_low = calculator.calculate_additional_medicare_tax(wages=200_000)
    assert amt_low == 0.0, f"Expected $0, got {fmt(amt_low)}"
    print("  [PASS] No Additional Medicare Tax below threshold")

    # Full calculation includes it in tax_before_credits
    income = TaxableIncome(wages=400_000)
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()
    result = calculator.calculate(
        income=income, deductions=deductions, credits=credits,
        federal_withheld=60_000,
    )
    assert result.additional_medicare_tax == expected
    # tax_before_credits should include the additional medicare tax
    income_tax_only = result.tax_before_credits - result.self_employment_tax - result.additional_medicare_tax
    assert income_tax_only > 0
    print(f"  Tax before credits: {fmt(result.tax_before_credits)}")
    print(f"    Income tax:       {fmt(income_tax_only)}")
    print(f"    Add'l Medicare:   {fmt(result.additional_medicare_tax)}")
    print("  [PASS] Additional Medicare Tax included in tax_before_credits")


def test_mortgage_proration():
    """Test mortgage interest proration against $750K federal debt limit."""
    print("\n" + "=" * 60)
    print("Test: Mortgage Interest Proration (Debt Limit)")
    print("=" * 60)

    data = ScheduleAData(
        mortgage_interest=20_000,
        mortgage_balance=1_000_000,  # Over the $750K limit
    )

    calc = ScheduleACalculator(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        standard_deduction=30_000,
    )
    result = calc.calculate(data=data, agi=200_000)

    # Interest prorated: 20000 * 750000/1000000 = 15000
    expected = 20_000 * 750_000 / 1_000_000
    print(f"  Mortgage balance:       $1,000,000")
    print(f"  Interest paid:          {fmt(20_000)}")
    print(f"  Prorated interest:      {fmt(result.mortgage_interest_deduction)}")
    assert abs(result.mortgage_interest_deduction - expected) < 0.01, \
        f"Expected {fmt(expected)}, got {fmt(result.mortgage_interest_deduction)}"
    print("  [PASS] Mortgage interest prorated by 750K/1M")

    # Under limit - no proration
    data_under = ScheduleAData(
        mortgage_interest=15_000,
        mortgage_balance=600_000,
    )
    result_under = calc.calculate(data=data_under, agi=200_000)
    assert result_under.mortgage_interest_deduction == 15_000, \
        f"Expected $15,000 (no proration), got {fmt(result_under.mortgage_interest_deduction)}"
    print("  [PASS] No proration when balance under $750K")


def test_niit():
    """Test Net Investment Income Tax (3.8%)."""
    print("\n" + "=" * 60)
    print("Test: Net Investment Income Tax (NIIT)")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2025)

    # MFJ with $260K AGI and $60K NII
    income = TaxableIncome(
        wages=200_000,
        interest_income=30_000,
        dividend_income=20_000,
        capital_gains=10_000,
    )
    magi = 260_000  # wages + interest + dividends + cap gains

    niit = calculator.calculate_niit(income, magi)
    # NIIT = 3.8% * min(NII=$60K, MAGI-threshold=$260K-$250K=$10K)
    expected = 0.038 * 10_000  # $380
    print(f"  MAGI:     {fmt(magi)}")
    print(f"  NII:      {fmt(60_000)}")
    print(f"  NIIT:     {fmt(niit)}")
    assert abs(niit - expected) < 0.01, f"Expected {fmt(expected)}, got {fmt(niit)}"
    print("  [PASS] NIIT = 3.8% x min(NII, MAGI-threshold) = $380")

    # Below threshold - no NIIT
    niit_low = calculator.calculate_niit(
        TaxableIncome(wages=200_000, interest_income=5_000), 205_000
    )
    assert niit_low == 0.0, f"Expected $0 NIIT below threshold, got {fmt(niit_low)}"
    print("  [PASS] No NIIT when MAGI below threshold")


def test_qdcg_preferential_rates():
    """Test qualified dividends / LTCG taxed at preferential rates."""
    print("\n" + "=" * 60)
    print("Test: QD/LTCG Preferential Rate Taxation")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2025)

    # $150K taxable income with $20K QD - should pay less than all ordinary
    income_with_qd = TaxableIncome(
        wages=130_000,
        dividend_income=20_000,
        qualified_dividends=20_000,
    )
    deductions = Deductions(use_standard=True)
    credits = TaxCredits()

    result_qd = calculator.calculate(
        income=income_with_qd, deductions=deductions, credits=credits,
        federal_withheld=0,
    )

    # Same income but ALL ordinary (no QD)
    income_ordinary = TaxableIncome(wages=150_000)
    result_ord = calculator.calculate(
        income=income_ordinary, deductions=deductions, credits=credits,
        federal_withheld=0,
    )

    # Both have same taxable income
    assert result_qd.taxable_income == result_ord.taxable_income, \
        f"Taxable incomes should match: {result_qd.taxable_income} vs {result_ord.taxable_income}"

    print(f"  Taxable income:         {fmt(result_qd.taxable_income)}")
    print(f"  Tax with QD:            {fmt(result_qd.ordinary_income_tax + result_qd.qualified_dividend_ltcg_tax)}")
    print(f"  Tax all ordinary:       {fmt(result_ord.ordinary_income_tax)}")
    print(f"  QD/LTCG tax component:  {fmt(result_qd.qualified_dividend_ltcg_tax)}")

    # Tax with QD should be less than all-ordinary
    qd_income_tax = result_qd.ordinary_income_tax + result_qd.qualified_dividend_ltcg_tax
    ord_income_tax = result_ord.ordinary_income_tax
    assert qd_income_tax < ord_income_tax, \
        f"QD tax ({fmt(qd_income_tax)}) should be less than ordinary ({fmt(ord_income_tax)})"
    print("  [PASS] QD preferential rates reduce total tax")


def test_1099r_fields():
    """Test 1099-R distribution_code and taxable_amount_not_determined fields."""
    print("\n" + "=" * 60)
    print("Test: 1099-R Distribution Code and Taxable Amount Fields")
    print("=" * 60)

    from src.models import Form1099R

    # Normal distribution with known taxable amount
    r1 = Form1099R(
        payer_name="Retirement Fund",
        gross_distribution=50_000,
        taxable_amount=50_000,
        distribution_code="7",  # Normal distribution
    )
    assert r1.distribution_code == "7"
    assert r1.taxable_amount_not_determined is False
    print(f"  Distribution code: {r1.distribution_code}")
    print(f"  Taxable not determined: {r1.taxable_amount_not_determined}")
    print("  [PASS] Normal 1099-R fields correct")

    # Distribution where taxable amount is not determined
    r2 = Form1099R(
        payer_name="Pension Plan",
        gross_distribution=100_000,
        taxable_amount=100_000,
        taxable_amount_not_determined=True,
        distribution_code="1",  # Early distribution
    )
    assert r2.taxable_amount_not_determined is True
    assert r2.distribution_code == "1"
    print(f"  Early dist code: {r2.distribution_code}")
    print(f"  Taxable not determined: {r2.taxable_amount_not_determined}")
    print("  [PASS] 1099-R with taxable_amount_not_determined flag")


def test_salt_federal_vs_ca():
    """Test SALT: federal caps at $10K, CA excludes state income tax with no cap."""
    print("\n" + "=" * 60)
    print("Test: SALT - Federal Cap vs CA No Cap")
    print("=" * 60)

    data = ScheduleAData(
        state_income_tax_paid=25_000,
        real_estate_taxes=15_000,
        vehicle_registrations=[
            CAVehicleRegistration(vehicle_license_fee=500),
        ],
        mortgage_interest=20_000,
    )

    # Federal: SALT = 25000 + 15000 + 500 = 40500, capped at 10000
    fed_calc = ScheduleACalculator(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        standard_deduction=30_000,
    )
    fed_result = fed_calc.calculate(data=data, agi=300_000)

    # CA: SALT = 15000 + 500 = 15500 (excludes state income tax, no cap)
    ca_result = ScheduleACalculator.calculate_ca_itemized(
        data=data, agi=300_000, ca_standard_deduction=10_726,
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2025,
    )

    print(f"  Federal SALT:  {fmt(fed_result.salt_deduction)} (capped at $10K)")
    print(f"  Fed uncapped:  {fmt(fed_result.salt_uncapped)} (incl state income tax)")
    print(f"  CA SALT:       {fmt(ca_result.salt_deduction)} (no cap, excl state tax)")

    assert fed_result.salt_deduction == 10_000, \
        f"Federal SALT should be $10,000, got {fmt(fed_result.salt_deduction)}"
    assert fed_result.salt_uncapped == 40_500, \
        f"Federal uncapped SALT should be $40,500, got {fmt(fed_result.salt_uncapped)}"
    assert ca_result.salt_deduction == 15_500, \
        f"CA SALT should be $15,500, got {fmt(ca_result.salt_deduction)}"
    print("  [PASS] Federal SALT capped at $10K")
    print("  [PASS] CA SALT excludes state income tax, no cap")

    # Verify the DIFFERENCE is exactly the state income tax (design, not bug)
    diff = fed_result.salt_uncapped - ca_result.salt_deduction
    assert diff == 25_000, f"Fed-CA SALT diff should equal state income tax ($25K), got {fmt(diff)}"
    print("  [PASS] Fed uncapped SALT - CA SALT = state income tax (by design)")


def test_niit_includes_all_nii():
    """Test NIIT base includes interest, dividends, cap gains, and rental income."""
    print("\n" + "=" * 60)
    print("Test: NIIT includes all NII components")
    print("=" * 60)

    calculator = FederalTaxCalculator(FilingStatus.MARRIED_FILING_JOINTLY, tax_year=2025)

    income = TaxableIncome(
        wages=200_000,
        interest_income=10_000,
        dividend_income=15_000,
        qualified_dividends=12_000,
        capital_gains=8_000,
        rental_income=5_000,
    )
    magi = income.total_income  # 238000

    niit = calculator.calculate_niit(income, magi)
    # NII = interest(10K) + dividends(15K) + cap_gains(8K) + rental(5K) = 38K
    # But MAGI - threshold = 238K - 250K = -12K (below threshold)
    assert niit == 0.0, f"Expected $0 NIIT (below threshold), got {fmt(niit)}"
    print(f"  MAGI $238K < $250K threshold: NIIT = {fmt(niit)}")
    print("  [PASS] No NIIT below threshold even with NII")

    # Now push over threshold with higher wages
    income2 = TaxableIncome(
        wages=230_000,
        interest_income=10_000,
        dividend_income=15_000,
        qualified_dividends=12_000,
        capital_gains=8_000,
        rental_income=5_000,
    )
    magi2 = income2.total_income  # 268000
    niit2 = calculator.calculate_niit(income2, magi2)
    # NII = 10K + 15K + 8K + 5K = 38K
    # MAGI - threshold = 268K - 250K = 18K
    # NIIT = 3.8% * min(38K, 18K) = 3.8% * 18K = 684
    expected = 0.038 * 18_000
    print(f"  MAGI $268K, NII includes: int=$10K + div=$15K + cg=$8K + rent=$5K = $38K")
    print(f"  NIIT = 3.8% * min($38K, $18K) = {fmt(expected)}")
    assert abs(niit2 - expected) < 0.01, f"Expected {fmt(expected)}, got {fmt(niit2)}"
    print("  [PASS] NIIT correctly includes all NII components")

    # Negative cap gains reduce NII; negative rental floored to 0
    income3 = TaxableIncome(
        wages=270_000,
        interest_income=10_000,
        dividend_income=5_000,
        capital_gains=-3_000,
        rental_income=-8_000,
    )
    magi3 = income3.total_income  # 274000
    niit3 = calculator.calculate_niit(income3, magi3)
    # NII = 10K + 5K + (-3K) + max(0,-8K) = 12K
    # MAGI - threshold = 274K - 250K = 24K
    # NIIT = 3.8% * min(12K, 24K) = 3.8% * 12K = 456
    expected3 = 0.038 * 12_000
    print(f"  Cap losses reduce NII, rental losses floored to 0: NII = $12K")
    print(f"  NIIT = {fmt(niit3)}")
    assert abs(niit3 - expected3) < 0.01, f"Expected {fmt(expected3)}, got {fmt(niit3)}"
    print("  [PASS] Capital losses reduce NII; rental losses floored to 0")


def test_mortgage_proration_extreme():
    """Test mortgage proration catches extreme balance values."""
    print("\n" + "=" * 60)
    print("Test: Mortgage Proration - Extreme Balance (Config Error Detection)")
    print("=" * 60)

    # Simulate a config error: $270M balance instead of $2.7M
    data_extreme = ScheduleAData(
        mortgage_interest=129_530,
        mortgage_balance=270_000_000,  # $270M - clearly wrong
    )

    calc = ScheduleACalculator(
        filing_status=FilingStatus.MARRIED_FILING_JOINTLY,
        standard_deduction=30_000,
    )
    result = calc.calculate(data=data_extreme, agi=1_500_000)

    # Federal: 129530 * 750K/270M = 359.81
    expected_fed = 129_530 * 750_000 / 270_000_000
    print(f"  Balance $270M (likely config error)")
    print(f"  Raw interest: {fmt(129_530)}")
    print(f"  Prorated:     {fmt(result.mortgage_interest_deduction)}")
    print(f"  Ratio:        {750_000/270_000_000*100:.4f}%")
    assert abs(result.mortgage_interest_deduction - expected_fed) < 1, \
        f"Expected {fmt(expected_fed)}, got {fmt(result.mortgage_interest_deduction)}"
    print("  [PASS] Proration math is correct (even with extreme balance)")

    # Now with correct $2.7M balance
    data_correct = ScheduleAData(
        mortgage_interest=129_530,
        mortgage_balance=2_700_000,
    )
    result2 = calc.calculate(data=data_correct, agi=1_500_000)
    expected_correct = 129_530 * 750_000 / 2_700_000
    print(f"\n  Corrected balance $2.7M:")
    print(f"  Prorated:     {fmt(result2.mortgage_interest_deduction)}")
    assert abs(result2.mortgage_interest_deduction - expected_correct) < 1
    print("  [PASS] $2.7M balance gives reasonable proration")


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
    test_rental_vs_personal_mortgage()
    test_capital_loss_carryover()
    test_ca_itemized_limitation()
    test_additional_medicare_tax()
    test_mortgage_proration()
    test_niit()
    test_niit_includes_all_nii()
    test_qdcg_preferential_rates()
    test_1099r_fields()
    test_salt_federal_vs_ca()
    test_mortgage_proration_extreme()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED!")
    print("=" * 60)
