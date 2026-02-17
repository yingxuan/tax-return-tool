#!/usr/bin/env python3
"""Discover AcroForm field names in a fillable PDF.

Usage:
    python tools/discover_fields.py <pdf_path>
    python tools/discover_fields.py pdf_templates/2024/f1040.pdf

Outputs each field's fully-qualified name, type, and current value (if any).
Use this to build field mappings for src/field_mappings/*.py modules.
"""

import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("Error: pypdf is not installed. Run: pip install pypdf>=4.0.0")
    sys.exit(1)


def discover_fields(pdf_path: str) -> None:
    """Print all AcroForm fields found in a PDF."""
    path = Path(pdf_path)
    if not path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    reader = PdfReader(str(path))
    fields = reader.get_fields()

    if not fields:
        print(f"No AcroForm fields found in {path.name}.")
        print("This PDF may use XFA forms (not supported by pypdf).")
        return

    print(f"Found {len(fields)} fields in {path.name}:")
    print("-" * 80)
    print(f"{'#':<5} {'Field Name':<60} {'Type':<12} {'Value'}")
    print("-" * 80)

    for i, (name, field_obj) in enumerate(sorted(fields.items()), 1):
        field_type = field_obj.get("/FT", "???")
        # /FT values: /Tx = text, /Btn = checkbox/radio, /Ch = choice
        type_map = {"/Tx": "Text", "/Btn": "Checkbox", "/Ch": "Choice"}
        type_str = type_map.get(str(field_type), str(field_type))

        value = field_obj.get("/V", "")
        if value:
            value = str(value)[:40]

        print(f"{i:<5} {name:<60} {type_str:<12} {value}")

    print("-" * 80)
    print(f"\nTotal: {len(fields)} fields")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    discover_fields(sys.argv[1])


if __name__ == "__main__":
    main()
