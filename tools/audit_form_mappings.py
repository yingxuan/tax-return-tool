#!/usr/bin/env python3
"""Audit PDF form mappers: spot-check that key totals match tax calculations.

Runs the pipeline (config or demo), invokes each form mapper, and compares
AGI, total tax, and refund/amount owed to federal_calculation and state_calculation.
Use after changing field mappings to catch drift.

Usage (from project root):
    python tools/audit_form_mappings.py --demo
    python tools/audit_form_mappings.py --config config/tax_profile.yaml
"""

import argparse
import sys
from pathlib import Path

# Run from project root so src is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _dollars(amount: float) -> str:
    return str(round(amount))


def run_audit(config_path: str | None, demo: bool) -> int:
    """Build tax return, run mappers, and compare key fields. Returns 0 if OK, 1 if mismatches."""
    from src.main import process_tax_documents, process_tax_return
    from src.config_loader import load_config
    from src.field_mappings import get_mapper, available_forms

    if demo:
        from src.main import run_demo
        tax_return = run_demo()
    else:
        config = load_config(config_path or "config/tax_profile.yaml")
        if not config:
            print("Error: Could not load config.")
            return 1
        tax_return = process_tax_documents(config=config)
        tax_return = process_tax_return(tax_return)

    fed = tax_return.federal_calculation
    state = tax_return.state_calculation
    year = tax_return.tax_year
    errors = []

    # --- Form 1040 ---
    try:
        mapper, _ = get_mapper("f1040")
        from src.field_mappings import f1040 as f1040_mod
        fields = f1040_mod.FIELD_NAMES.get(year, f1040_mod.FIELD_NAMES_2025)
        result = mapper(tax_return)
        if not result:
            print("  f1040: mapper returned no fields (skip audit)")
        else:
            if fed:
                agi_key = fields["line11a_agi"]
                if result.get(agi_key) != _dollars(fed.adjusted_gross_income):
                    errors.append(
                        f"f1040 line11a_agi: mapped={result.get(agi_key)!r} "
                        f"expected={_dollars(fed.adjusted_gross_income)!r}"
                    )
                tax_key = fields["line24_total_tax"]
                income_tax = fed.ordinary_income_tax + fed.qualified_dividend_ltcg_tax
                tax_minus_credits = max(0, income_tax - fed.credits)
                other_taxes = fed.self_employment_tax + fed.additional_medicare_tax + fed.niit
                expected_tax = _dollars(tax_minus_credits + other_taxes)
                if result.get(tax_key) != expected_tax:
                    errors.append(
                        f"f1040 line24_total_tax: mapped={result.get(tax_key)!r} expected={expected_tax!r}"
                    )
                ref = fed.refund_or_owed
                if ref > 0:
                    rkey = fields["line35a_refund"]
                    if result.get(rkey) != _dollars(ref):
                        errors.append(f"f1040 line35a_refund: mapped={result.get(rkey)!r} expected={_dollars(ref)!r}")
                elif ref < 0:
                    okey = fields["line37_amount_owed"]
                    if result.get(okey) != _dollars(abs(ref)):
                        errors.append(f"f1040 line37_amount_owed: mapped={result.get(okey)!r} expected={_dollars(abs(ref))!r}")
    except Exception as e:
        errors.append(f"f1040: {e}")

    # --- CA 540 ---
    if state and state.jurisdiction == "California":
        try:
            mapper, _ = get_mapper("ca540")
            from src.field_mappings import ca540 as ca540_mod
            fields = ca540_mod.FIELD_NAMES.get(year, ca540_mod.FIELD_NAMES_2025)
            result = mapper(tax_return)
            if not result:
                print("  ca540: mapper returned no fields (skip audit)")
            else:
                if result.get(fields["line17_ca_agi"]) != _dollars(state.adjusted_gross_income):
                    errors.append(
                        f"ca540 line17_ca_agi: mapped={result.get(fields['line17_ca_agi'])!r} "
                        f"expected={_dollars(state.adjusted_gross_income)!r}"
                    )
                total_tax = state.tax_after_credits + getattr(state, "ca_mental_health_tax", 0)
                if result.get(fields["line64_total_tax"]) != _dollars(total_tax):
                    errors.append(
                        f"ca540 line64_total_tax: mapped={result.get(fields['line64_total_tax'])!r} "
                        f"expected={_dollars(total_tax)!r}"
                    )
                ref = state.refund_or_owed
                if ref > 0 and result.get(fields["line99_refund"]) != _dollars(ref):
                    errors.append(f"ca540 line99_refund: mapped={result.get(fields['line99_refund'])!r} expected={_dollars(ref)!r}")
                elif ref < 0 and result.get(fields["line100_amount_owed"]) != _dollars(abs(ref)):
                    errors.append(f"ca540 line100_amount_owed: mapped={result.get(fields['line100_amount_owed'])!r} expected={_dollars(abs(ref))!r}")
        except Exception as e:
            errors.append(f"ca540: {e}")

    if errors:
        print("Audit FAILED (mapped values do not match calculations):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("Audit OK: key mapper values match federal/state calculations.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PDF form mappers against tax calculations.")
    parser.add_argument("--config", default=None, help="Path to tax_profile YAML (default: config/tax_profile.yaml)")
    parser.add_argument("--demo", action="store_true", help="Use demo data instead of config")
    args = parser.parse_args()
    if not args.demo and not args.config:
        args.config = "config/tax_profile.yaml"
    return run_audit(config_path=args.config, demo=args.demo)


if __name__ == "__main__":
    sys.exit(main())
