#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare tool output to CPA 2024 data (from 2024.pdf).
Usage: python compare_with_cpa.py --config config/tax_profile.yaml [--tax-year 2024] [--quiet]
"""

import argparse
import sys
from pathlib import Path


# CPA 2024 参考数据（来自 2024.pdf）
CPA_2024_FEDERAL = {
    "Wages, salaries, tips": 2_069_937,
    "Interest income": 6_339,
    "Dividend income": 18_711,
    "Taxable IRA distributions": 9,
    "Capital gain or loss": -3_000,
    "Other income": 600,
    "Total income / AGI": 2_092_596,
    "Adjustments": 0,
    "SALT (Taxes)": 10_000,
    "Mortgage interest": 27_183,
    "Charitable contributions": 1_205,
    "Total itemized": 38_388,
    "Standard deduction": 29_200,
    "Deduction used": 38_388,
    "Taxable income": 2_054_155,
    "Tax before credits": 683_481,
    "Other taxes (Add'l Medicare + NIIT)": 17_499,
    "Total tax": 700_980,
    "Federal withheld": 607_058,
    "Estimated tax payments": 100_000,
    "Total payments": 707_058,
    "Refund (positive) / Owed (negative)": 6_078,  # CPA overpaid 6,078
}

CPA_2024_CA = {
    "CA AGI": 2_088_262,
    "CA itemized deductions": 17_212,
    "CA standard deduction": 11_080,
    "CA deduction used": 17_212,
    "CA taxable income": 2_071_050,
    "CA tax": 217_529,
    "Mental health tax": 10_711,
    "CA total tax": 228_240,
    "CA withheld": 218_294,
    "CA estimated": 10_000,
    "CA refund (positive) / owed (negative)": 54,  # CPA overpaid 54
}


def _diff(cpa: float, tool: float) -> str:
    d = tool - cpa
    if abs(d) < 0.02:
        return "-"
    return f"{d:+,.2f}"


def _ok(cpa: float, tool: float, tol: float = 1.0) -> str:
    if abs(tool - cpa) <= tol:
        return "OK"
    return "--"


def run():
    parser = argparse.ArgumentParser(description="Compare tool output with CPA 2024 data")
    parser.add_argument("--config", default="config/tax_profile.yaml", help="Config YAML path")
    parser.add_argument("--tax-year", type=int, default=None, help="Tax year (default from config)")
    parser.add_argument("--quiet", action="store_true", help="Suppress extraction/ingestion prints")
    args = parser.parse_args()

    # Add src to path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from src.config_loader import load_config
    from src.main import process_tax_documents, process_tax_return

    config = load_config(args.config)
    if not config:
        print("Failed to load config")
        sys.exit(1)
    if args.tax_year:
        config.tax_year = args.tax_year

    if args.quiet:
        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
            tax_return = process_tax_documents(config=config)
    else:
        tax_return = process_tax_documents(config=config)

    fed = tax_return.federal_calculation
    state = tax_return.state_calculation
    inc = tax_return.income
    if not fed or not state:
        print("No federal or state calculation; run with full config and documents.")
        sys.exit(1)

    # Build tool values for 2024 (same keys as CPA)
    yr = tax_return.tax_year
    if yr != 2024:
        print(f"Warning: tax year is {yr}; CPA reference is 2024. Comparison may be off.\n")

    sched_a = fed.schedule_a_result
    tool_fed = {
        "Wages, salaries, tips": round(inc.wages, 2),
        "Interest income": round(inc.interest_income, 2),
        "Dividend income": round(inc.dividend_income, 2),
        "Taxable IRA distributions": round(inc.retirement_income, 2),
        "Capital gain or loss": round(inc.capital_gains, 2),
        "Other income": round(inc.other_income, 2),
        "Total income / AGI": round(fed.gross_income, 2),
        "Adjustments": round(fed.adjustments, 2),
        "SALT (Taxes)": round(sched_a.salt_deduction, 2) if sched_a else 0,
        "Mortgage interest": round(sched_a.mortgage_interest_deduction, 2) if sched_a else 0,
        "Charitable contributions": round(sched_a.charitable_deduction, 2) if sched_a else 0,
        "Total itemized": round(sched_a.total_itemized, 2) if sched_a else 0,
        "Standard deduction": round(sched_a.standard_deduction, 2) if sched_a else 0,
        "Deduction used": round(fed.deductions, 2),
        "Taxable income": round(fed.taxable_income, 2),
        "Tax before credits": round(fed.tax_before_credits - (fed.additional_medicare_tax + fed.niit), 2),
        "Other taxes (Add'l Medicare + NIIT)": round(fed.additional_medicare_tax + fed.niit, 2),
        "Total tax": round(fed.tax_after_credits, 2),
        "Federal withheld": round(fed.tax_withheld, 2),
        "Estimated tax payments": round(fed.estimated_payments, 2),
        "Total payments": round(fed.total_payments, 2),
        "Refund (positive) / Owed (negative)": round(fed.refund_or_owed, 2),  # + = overpaid/refund, - = owe
    }

    ca_sched = state.schedule_a_result
    tool_ca = {
        "CA AGI": round(state.adjusted_gross_income, 2),
        "CA itemized deductions": round(ca_sched.total_itemized, 2) if ca_sched else 0,
        "CA standard deduction": round(ca_sched.standard_deduction, 2) if ca_sched else 0,
        "CA deduction used": round(state.deductions, 2),
        "CA taxable income": round(state.taxable_income, 2),
        "CA tax": round(state.tax_before_credits - state.ca_mental_health_tax, 2),
        "Mental health tax": round(state.ca_mental_health_tax, 2),
        "CA total tax": round(state.tax_after_credits, 2),
        "CA withheld": round(state.tax_withheld, 2),
        "CA estimated": round(state.estimated_payments, 2),
        "CA refund (positive) / owed (negative)": round(state.refund_or_owed, 2),  # + = overpaid, - = owe
    }

    # Print comparison
    w = 42
    print("\n" + "=" * 100)
    print("  2024 FEDERAL (Form 1040) - CPA vs Tool line-by-line")
    print("=" * 100)
    print(f"  {'Item':<{w}} {'CPA':>15} {'Tool':>15} {'Diff':>12} {'':>3}")
    print("-" * 100)
    for key in CPA_2024_FEDERAL:
        cpa = CPA_2024_FEDERAL[key]
        tool = tool_fed.get(key, 0)
        print(f"  {key:<{w}} {cpa:>15,.2f} {tool:>15,.2f} {_diff(cpa, tool):>12} {_ok(cpa, tool):>3}")
    print("=" * 100)

    print("\n" + "=" * 100)
    print("  2024 CALIFORNIA (Form 540) - CPA vs Tool line-by-line")
    print("=" * 100)
    print(f"  {'Item':<{w}} {'CPA':>15} {'Tool':>15} {'Diff':>12} {'':>3}")
    print("-" * 100)
    for key in CPA_2024_CA:
        cpa = CPA_2024_CA[key]
        tool = tool_ca.get(key, 0)
        print(f"  {key:<{w}} {cpa:>15,.2f} {tool:>15,.2f} {_diff(cpa, tool):>12} {_ok(cpa, tool):>3}")
    print("=" * 100)

    # Net owed summary
    rf, ro = tool_fed["Refund (positive) / Owed (negative)"], tool_ca["CA refund (positive) / owed (negative)"]
    print("\n  Summary:")
    print(f"    CPA:  Federal overpaid {CPA_2024_FEDERAL['Refund (positive) / Owed (negative)']:,.2f}  CA overpaid {CPA_2024_CA['CA refund (positive) / owed (negative)']:,.2f}")
    print(f"    Tool: Federal {'overpaid' if rf > 0 else 'owed'} ${abs(rf):,.2f}  CA {'overpaid' if ro > 0 else 'owed'} ${abs(ro):,.2f}")
    print()


if __name__ == "__main__":
    run()
