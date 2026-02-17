"""PDF form filler - generates filled IRS/FTB tax form PDFs.

Uses pypdf to fill AcroForm fields in official IRS/FTB fillable PDF templates
with computed tax return values.

Usage:
    from src.form_filler import generate_all_forms
    generate_all_forms(tax_return, output_dir="output/2024")
"""

from pathlib import Path
from typing import Dict, List, Optional

from .models import TaxReturn
from .field_mappings import get_mapper, available_forms

# Base directory for PDF templates (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = _PROJECT_ROOT / "pdf_templates"


def get_template_path(form_name: str, tax_year: int) -> Path:
    """Resolve the path to a blank PDF template.

    Looks in pdf_templates/<year>/<filename>, falling back to the
    most recent available year.
    """
    _, template_file = get_mapper(form_name)

    # Try exact year first, then fall back
    for year in [tax_year, 2024, 2025]:
        path = TEMPLATES_DIR / str(year) / template_file
        if path.exists():
            return path

    raise FileNotFoundError(
        f"PDF template not found for {form_name} ({template_file}). "
        f"Place the fillable PDF at: {TEMPLATES_DIR / str(tax_year) / template_file}"
    )


def fill_form(form_name: str, tax_return: TaxReturn) -> Optional[object]:
    """Fill a PDF form template with tax return data.

    Args:
        form_name: Registered form name (e.g., "f1040", "schedule_a")
        tax_return: Computed TaxReturn with all calculations done

    Returns:
        PdfWriter with filled fields, or None if no data to fill
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("Error: pypdf is not installed. Run: pip install pypdf>=4.0.0")
        return None

    mapper_fn, _ = get_mapper(form_name)
    field_values = mapper_fn(tax_return)

    if not field_values:
        return None

    template_path = get_template_path(form_name, tax_return.tax_year)
    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)

    # Fill form fields
    for page_num in range(len(writer.pages)):
        writer.update_page_form_field_values(
            writer.pages[page_num],
            field_values,
            auto_regenerate=False,
        )

    return writer


def fill_and_save(
    form_name: str,
    tax_return: TaxReturn,
    output_path: str,
) -> bool:
    """Fill a PDF form and save to disk.

    Args:
        form_name: Registered form name
        tax_return: Computed TaxReturn
        output_path: Where to write the filled PDF

    Returns:
        True if the file was written, False if skipped (no data)
    """
    writer = fill_form(form_name, tax_return)
    if writer is None:
        return False

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "wb") as f:
        writer.write(f)

    return True


def _auto_select_forms(tax_return: TaxReturn) -> List[str]:
    """Auto-select which forms to generate based on tax return data.

    Returns list of form names that are applicable.
    """
    forms = ["f1040"]  # Always generate 1040

    fed = tax_return.federal_calculation

    # Schedule A if itemizing
    if fed and fed.schedule_a_result and fed.schedule_a_result.use_itemized:
        forms.append("schedule_a")

    # Schedule B if interest or dividends > $1,500
    inc = tax_return.income
    if inc.interest_income > 1500 or inc.dividend_income > 1500:
        forms.append("schedule_b")

    # Schedule E if rental properties
    if tax_return.rental_properties:
        forms.append("schedule_e")

    # CA 540 if California resident
    if tax_return.state_calculation and tax_return.state_calculation.jurisdiction == "California":
        forms.append("ca540")

    return forms


def generate_all_forms(
    tax_return: TaxReturn,
    output_dir: str = "",
    forms: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Generate all applicable filled PDF forms.

    Args:
        tax_return: Computed TaxReturn
        output_dir: Directory to write PDFs (default: output/<year>/)
        forms: Specific forms to generate (default: auto-select)

    Returns:
        Dict mapping form_name -> output file path for forms that were generated
    """
    if not output_dir:
        output_dir = str(_PROJECT_ROOT / "output" / str(tax_return.tax_year))

    if forms is None:
        forms = _auto_select_forms(tax_return)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    generated = {}
    skipped = []
    errors = []

    for form_name in forms:
        try:
            # Check if template exists
            template = get_template_path(form_name, tax_return.tax_year)
        except FileNotFoundError as e:
            errors.append((form_name, str(e)))
            continue

        _, template_file = get_mapper(form_name)
        out_file = output_path / f"filled_{template_file}"

        success = fill_and_save(form_name, tax_return, str(out_file))
        if success:
            generated[form_name] = str(out_file)
        else:
            skipped.append(form_name)

    # Print summary
    if generated:
        print(f"\nGenerated {len(generated)} PDF form(s) in {output_dir}:")
        for name, path in generated.items():
            print(f"  {name}: {Path(path).name}")

    if skipped:
        print(f"\nSkipped {len(skipped)} form(s) (no applicable data):")
        for name in skipped:
            print(f"  {name}")

    if errors:
        print(f"\nMissing templates ({len(errors)}):")
        for name, err in errors:
            print(f"  {name}: {err}")

    return generated
