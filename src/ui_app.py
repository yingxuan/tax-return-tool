"""Simple Web UI for the tax return tool.

Provides manual input, folder path, and file upload/drag-drop; calls existing
process_tax_documents / process_tax_return / generate_full_report without
changing core logic.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from flask import Flask, request, render_template_string, jsonify

# Import existing pipeline; no changes to these modules
from .config_loader import load_config, TaxProfileConfig, US_STATES
from .main import process_tax_documents, process_tax_return
from .report_generator import generate_full_report, generate_full_report_html

app = Flask(__name__)


def _float(form, key: str, default: float = 0.0) -> float:
    val = form.get(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _int(form, key: str, default: int = 0) -> int:
    val = form.get(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def config_from_form(form) -> TaxProfileConfig:
    """Build TaxProfileConfig from form data; defaults match config_loader."""
    document_folder = (form.get("document_folder") or "").strip() or None
    filing_status = (form.get("filing_status") or "single").strip().lower()
    state_of_residence = (form.get("state_of_residence") or "CA").strip().upper()
    if len(state_of_residence) != 2:
        state_of_residence = "CA"
    keywords_str = (form.get("rental_1098_keywords") or "").strip()
    rental_1098_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    return TaxProfileConfig(
        tax_year=_int(form, "tax_year", 2025),
        taxpayer_name=(form.get("taxpayer_name") or "Taxpayer").strip(),
        taxpayer_ssn=(form.get("taxpayer_ssn") or "").strip() or None,
        spouse_ssn=(form.get("spouse_ssn") or "").strip() or None,
        filing_status=filing_status,
        age=_int(form, "age", 30),
        state_of_residence=state_of_residence,
        is_ca_resident=(state_of_residence == "CA"),
        is_renter=form.get("is_renter") in ("true", "1", "on", "yes"),
        dependents=[],
        document_folder=document_folder,
        rental_1098_keywords=rental_1098_keywords,
        capital_loss_carryover=_float(form, "capital_loss_carryover"),
        short_term_loss_carryover=_float(form, "short_term_loss_carryover"),
        long_term_loss_carryover=_float(form, "long_term_loss_carryover"),
        pal_carryover=_float(form, "pal_carryover"),
        personal_mortgage_balance=_float(form, "personal_mortgage_balance"),
        us_treasury_interest=_float(form, "us_treasury_interest"),
        charitable_contributions=_float(form, "charitable_contributions"),
        ca_misc_deductions=_float(form, "ca_misc_deductions"),
        federal_estimated_payments=_float(form, "federal_estimated_payments"),
        ca_estimated_payments=_float(form, "ca_estimated_payments"),
        federal_withheld_adjustment=_float(form, "federal_withheld_adjustment"),
        other_income=_float(form, "other_income"),
        qualified_dividends=_float(form, "qualified_dividends"),
        ordinary_dividends=_float(form, "ordinary_dividends"),
        primary_property_tax=_float(form, "primary_property_tax"),
        primary_home_apn=(form.get("primary_home_apn") or "").strip(),
        rental_properties=[],
    )


def _apply_form_overrides(config: TaxProfileConfig, form) -> TaxProfileConfig:
    """Override config with form values (for when YAML was uploaded)."""
    config.tax_year = _int(form, "tax_year", config.tax_year)
    config.taxpayer_name = (form.get("taxpayer_name") or config.taxpayer_name).strip()
    tp_ssn = (form.get("taxpayer_ssn") or "").strip()
    if tp_ssn:
        config.taxpayer_ssn = tp_ssn
    sp_ssn = (form.get("spouse_ssn") or "").strip()
    if sp_ssn:
        config.spouse_ssn = sp_ssn
    fs = form.get("filing_status")
    if fs:
        config.filing_status = fs.strip().lower()
    config.age = _int(form, "age", config.age)
    so = (form.get("state_of_residence") or "").strip().upper()
    if len(so) == 2:
        config.state_of_residence = so
    config.is_ca_resident = config.state_of_residence == "CA"
    config.is_renter = form.get("is_renter") in ("true", "1", "on", "yes")
    doc_folder = (form.get("document_folder") or "").strip()
    if doc_folder:
        config.document_folder = doc_folder
    keywords_str = (form.get("rental_1098_keywords") or "").strip()
    if keywords_str:
        config.rental_1098_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    config.capital_loss_carryover = _float(form, "capital_loss_carryover", config.capital_loss_carryover)
    config.short_term_loss_carryover = _float(form, "short_term_loss_carryover", config.short_term_loss_carryover)
    config.long_term_loss_carryover = _float(form, "long_term_loss_carryover", config.long_term_loss_carryover)
    config.pal_carryover = _float(form, "pal_carryover", config.pal_carryover)
    config.personal_mortgage_balance = _float(form, "personal_mortgage_balance", config.personal_mortgage_balance)
    config.us_treasury_interest = _float(form, "us_treasury_interest", config.us_treasury_interest)
    config.charitable_contributions = _float(form, "charitable_contributions", config.charitable_contributions)
    config.ca_misc_deductions = _float(form, "ca_misc_deductions", config.ca_misc_deductions)
    config.federal_estimated_payments = _float(form, "federal_estimated_payments", config.federal_estimated_payments)
    config.ca_estimated_payments = _float(form, "ca_estimated_payments", config.ca_estimated_payments)
    config.federal_withheld_adjustment = _float(form, "federal_withheld_adjustment", config.federal_withheld_adjustment)
    config.other_income = _float(form, "other_income", config.other_income)
    config.qualified_dividends = _float(form, "qualified_dividends", config.qualified_dividends)
    config.ordinary_dividends = _float(form, "ordinary_dividends", config.ordinary_dividends)
    config.primary_property_tax = _float(form, "primary_property_tax", config.primary_property_tax)
    apn = (form.get("primary_home_apn") or "").strip()
    if apn:
        config.primary_home_apn = apn
    return config


@app.route("/")
def index():
    """Serve the single-page UI."""
    state_options = "\n".join(
        f'<option value="{code}"{" selected" if code == "CA" else ""}>{name}</option>'
        for code, name in US_STATES
    )
    return render_template_string(INDEX_HTML, state_options=state_options)


def _clean_1098_display_address(property_address: str, lender_name: str) -> str:
    """Use 1098 Box 8 address for display; strip form placeholder text and prefer real address."""
    addr = (property_address or "").strip()
    if not addr:
        return lender_name or "Unknown"
    # Common PDF form labels that get captured instead of the actual address
    placeholder_patterns = (
        "street address", "city or town", "state or province", "zip or",
        "address and telephone", "country, zip", "for this mortgage",
    )
    lower = addr.lower()
    if any(p in lower for p in placeholder_patterns):
        # Try to extract real address from parentheses, e.g. "address and telephone number (10886 LINDA VISTA DR)"
        m = re.search(r"\(([^)]{5,})\)", addr)
        if m:
            return m.group(1).strip()
        return lender_name or "Unknown"
    return addr


def _detect_missing(tax_return) -> dict:
    """Return missing field keys and any extra metadata (e.g. 1098 lender options)."""
    missing = []
    extras = {}
    sa = tax_return.schedule_a_data

    # Charitable contributions
    if not sa or sa.cash_contributions == 0:
        missing.append("charitable_contributions")

    # Property tax: if multiple parcels detected, ask user to pick primary home
    parcels = getattr(tax_return, '_property_tax_parcels', None)
    if parcels:
        missing.append("primary_home_apn")
        extras["parcel_options"] = [
            {"apn": p.apn, "address": p.address, "amount": p.amount}
            for p in parcels
        ]
    elif not sa or sa.real_estate_taxes == 0:
        missing.append("primary_property_tax")

    # Mortgage balance (only relevant if there's a mortgage)
    has_mortgage = any(not f.is_rental for f in tax_return.form_1098)
    if has_mortgage and (not sa or sa.mortgage_balance == 0):
        missing.append("personal_mortgage_balance")

    # Estimated payments
    fed_est = sum(p.amount for p in tax_return.estimated_payments if p.jurisdiction == "federal")
    ca_est = sum(p.amount for p in tax_return.estimated_payments if p.jurisdiction == "california")
    if fed_est == 0:
        missing.append("federal_estimated_payments")
    if ca_est == 0:
        missing.append("ca_estimated_payments")

    # Capital loss carryover (never auto-extracted)
    missing.append("capital_loss_carryover")

    # Rental 1098: if multiple 1098s and none tagged rental, ask user to pick
    if len(tax_return.form_1098) > 1 and not any(f.is_rental for f in tax_return.form_1098):
        missing.append("rental_1098_keywords")
        extras["lender_options"] = [
            {
                "lender": f.lender_name,
                "interest": f.mortgage_interest,
                "address": f.property_address or "",
                "display_label": _clean_1098_display_address(f.property_address or "", f.lender_name),
            }
            for f in tax_return.form_1098
        ]

    return {"missing": missing, **extras}


@app.route("/run", methods=["POST"])
def run():
    """Process form + optional config YAML + optional document files; return report."""
    form = request.form
    config = None
    config_temp_path = None
    doc_temp_dir = None
    saved_paths = []

    try:
        # Optional: load config from uploaded YAML
        config_file = request.files.get("config_file")
        if config_file and config_file.filename:
            fd, config_temp_path = tempfile.mkstemp(suffix=".yaml")
            os.close(fd)
            config_file.save(config_temp_path)
            config = load_config(config_temp_path)
            if config is None:
                return jsonify({"error": "Failed to load config from uploaded YAML."}), 400
            config = _apply_form_overrides(config, form)
        else:
            config = config_from_form(form)

        # Document source: uploaded files take priority over folder path
        document_files = request.files.getlist("documents")
        has_uploads = any(f and f.filename for f in document_files)

        if has_uploads:
            doc_temp_dir = tempfile.mkdtemp()
            for f in document_files:
                if not f or not f.filename:
                    continue
                safe_name = Path(f.filename).name or "upload"
                dest = os.path.join(doc_temp_dir, safe_name)
                f.save(dest)
                saved_paths.append(dest)
            if not saved_paths:
                return jsonify({"error": "No valid document files received."}), 400
            tax_return = process_tax_documents(
                local_files=saved_paths,
                config=config,
            )
        else:
            document_folder = (form.get("document_folder") or "").strip() or None
            if not document_folder:
                return jsonify({
                    "error": "Provide either a document folder path or drag-and-drop files."
                }), 400
            tax_return = process_tax_documents(
                local_folder=document_folder,
                config=config,
            )

        report = generate_full_report(tax_return)
        report_html = generate_full_report_html(tax_return)
        info = _detect_missing(tax_return)
        return jsonify({"report": report, "report_html": report_html, **info})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if config_temp_path and os.path.isfile(config_temp_path):
            try:
                os.unlink(config_temp_path)
            except OSError:
                pass
        if doc_temp_dir and os.path.isdir(doc_temp_dir):
            try:
                shutil.rmtree(doc_temp_dir)
            except OSError:
                pass


# Inline HTML template (single page: form, drop zone, report area)
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tax Return Tool</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #f0f2f5; color: #1a1a1a; }
    .container { max-width: 760px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
    h1 { font-size: 1.6rem; margin-bottom: 0.25rem; font-weight: 700;
         background: linear-gradient(135deg, #1a56db, #0ea5e9); -webkit-background-clip: text;
         -webkit-text-fill-color: transparent; background-clip: text; }
    .subtitle { color: #64748b; margin-bottom: 1.5rem; font-size: 0.93rem; line-height: 1.5; }

    /* Privacy banner */
    .banner { display: flex; align-items: flex-start; gap: 0.5rem; background: #ecfdf5; border: 1px solid #a7f3d0;
              border-radius: 10px; padding: 0.65rem 0.9rem; margin-bottom: 1.25rem; font-size: 0.88rem; color: #065f46; }
    .banner svg { flex-shrink: 0; margin-top: 2px; }

    /* Steps */
    .step { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.3rem 1.3rem 1.1rem;
            margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            transition: box-shadow 0.2s, transform 0.2s; }
    .step:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04); }
    .step-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
    .step-num { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
                border-radius: 50%; background: linear-gradient(135deg, #1a56db, #3b82f6); color: #fff;
                font-size: 0.85rem; font-weight: 700; flex-shrink: 0; }
    .step-title { font-size: 1.08rem; font-weight: 600; color: #1e293b; }

    /* Form fields */
    label { display: block; margin-top: 0.75rem; font-weight: 500; font-size: 0.92rem; color: #334155; }
    label:first-child { margin-top: 0; }
    .label-hint { font-weight: 400; color: #94a3b8; font-size: 0.84rem; }
    input[type="text"], input[type="number"], select {
      width: 100%; padding: 0.5rem 0.65rem; margin-top: 0.25rem; border: 1.5px solid #cbd5e1;
      border-radius: 8px; font-size: 0.92rem; background: #f8fafc;
      transition: border-color 0.2s, box-shadow 0.2s, background 0.2s; }
    input[type="text"]:hover, input[type="number"]:hover, select:hover { border-color: #94a3b8; }
    input[type="text"]:focus, input[type="number"]:focus, select:focus {
      outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.15); background: #fff; }
    input[type="number"].input-valid { border-color: #22c55e; background: #f0fdf4; }
    input[type="number"].input-invalid { border-color: #ef4444; background: #fef2f2; }
    .field-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    .field-row > * { flex: 1; min-width: 140px; }
    .checkbox-row { display: flex; gap: 1.25rem; align-items: center; margin-top: 0.75rem; }
    .checkbox-row label { margin-top: 0; font-weight: 400; cursor: pointer; display: flex; align-items: center; gap: 0.35rem; }
    .hint { font-size: 0.82rem; color: #94a3b8; margin-top: 0.2rem; line-height: 1.3; }

    /* Drop zone */
    .drop-zone {
      border: 2px dashed #94a3b8; border-radius: 12px; padding: 1.5rem; text-align: center;
      margin-top: 0.75rem; background: #f8fafc; transition: all 0.2s ease; cursor: pointer; }
    .drop-zone:hover { border-color: #3b82f6; background: #eff6ff; }
    .drop-zone.dragover { border-color: #3b82f6; background: #dbeafe; border-style: solid; }
    .drop-zone-icon { font-size: 2rem; margin-bottom: 0.4rem; }
    .drop-zone p { margin: 0.25rem 0; color: #64748b; font-size: 0.9rem; }
    .drop-zone .browse-links { margin-top: 0.5rem; }
    .link-btn { background: none; border: none; color: #3b82f6; cursor: pointer; padding: 0.2rem 0.4rem;
                font-size: 0.9rem; text-decoration: underline; font-weight: 500; transition: color 0.15s; }
    .link-btn:hover { color: #1d4ed8; }
    .file-list { font-size: 0.84rem; color: #475569; text-align: left; max-height: 140px; overflow: auto;
                 margin-top: 0.6rem; padding: 0 0.25rem; }
    .file-item { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0.35rem; border-radius: 4px; }
    .file-item:hover { background: #f1f5f9; }
    .file-icon { font-size: 0.9rem; flex-shrink: 0; width: 1.2rem; text-align: center; }
    .file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-actions { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem; justify-content: center; }
    .file-count { display: inline-flex; align-items: center; gap: 0.3rem; background: #dbeafe; color: #1e40af;
                  font-size: 0.82rem; padding: 0.2rem 0.65rem; border-radius: 12px; font-weight: 600;
                  transition: transform 0.2s; }
    .file-count.pop { animation: pop 0.3s ease; }
    @keyframes pop { 0% { transform: scale(1); } 50% { transform: scale(1.15); } 100% { transform: scale(1); } }
    .clear-btn { background: none; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.15rem 0.5rem;
                 font-size: 0.8rem; color: #64748b; cursor: pointer; transition: all 0.15s; }
    .clear-btn:hover { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }
    .or-divider { display: flex; align-items: center; gap: 0.75rem; margin: 0.9rem 0; color: #94a3b8; font-size: 0.85rem; }
    .or-divider::before, .or-divider::after { content: ""; flex: 1; border-top: 1px solid #e2e8f0; }

    /* Collapsible advanced */
    .toggle-btn { background: none; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.5rem 0.85rem;
                  cursor: pointer; font-size: 0.9rem; color: #475569; display: flex; align-items: center;
                  gap: 0.4rem; margin-top: 0.75rem; width: 100%; transition: all 0.15s; }
    .toggle-btn:hover { background: #f8fafc; border-color: #94a3b8; }
    .toggle-arrow { transition: transform 0.2s; font-size: 0.75rem; }
    .toggle-arrow.open { transform: rotate(90deg); }
    .collapsible { display: none; margin-top: 0.5rem; }
    .collapsible.open { display: block; }
    .field-group { border-left: 3px solid #e2e8f0; padding-left: 0.85rem; margin-top: 0.75rem; }
    .field-group-title { font-size: 0.82rem; font-weight: 600; color: #94a3b8; text-transform: uppercase;
                         letter-spacing: 0.04em; margin-bottom: 0.25rem; }

    /* Step 3 fade-in */
    .step-fadein { animation: fadeSlideIn 0.4s ease-out; }
    @keyframes fadeSlideIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

    /* Run button */
    .run-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%;
               padding: 0.8rem; margin-top: 1.25rem; cursor: pointer;
               background: linear-gradient(135deg, #1a56db, #3b82f6); color: #fff;
               border: none; border-radius: 10px; font-size: 1rem; font-weight: 600;
               transition: all 0.2s; box-shadow: 0 2px 8px rgba(26,86,219,0.25); }
    .run-btn:hover { box-shadow: 0 4px 16px rgba(26,86,219,0.35); transform: translateY(-1px); }
    .run-btn:active { transform: translateY(0); }
    .run-btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; box-shadow: none; }
    .run-btn.pulse { animation: btnPulse 1.5s ease-in-out infinite; }
    @keyframes btnPulse { 0%, 100% { box-shadow: 0 2px 8px rgba(26,86,219,0.25); }
                          50% { box-shadow: 0 2px 20px rgba(26,86,219,0.5); } }
    .spinner { display: none; width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3);
               border-top-color: #fff; border-radius: 50%; animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Loading overlay */
    .loading-overlay { display: none; position: fixed; inset: 0; background: rgba(15,23,42,0.4);
                       backdrop-filter: blur(4px); z-index: 1000; align-items: center; justify-content: center;
                       flex-direction: column; gap: 1rem; }
    .loading-overlay.active { display: flex; }
    .overlay-spinner { width: 44px; height: 44px; border: 3px solid rgba(255,255,255,0.2);
                       border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; }
    .overlay-text { color: #fff; font-size: 1rem; font-weight: 500; }

    /* Report */
    .error-msg { color: #dc2626; margin-top: 0.75rem; font-size: 0.9rem; padding: 0.6rem 0.85rem;
                 background: #fef2f2; border-radius: 8px; border: 1px solid #fecaca; }
    .error-msg:empty { display: none; }
    #report { margin-top: 1rem; }
    #report:empty { display: none; }
    .report-fadein { animation: fadeSlideIn 0.5s ease-out; }
    .report-toolbar { display: flex; gap: 0.5rem; justify-content: flex-end; margin-bottom: 0.75rem; }
    .report-toolbar button { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.35rem 0.7rem;
                             border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; font-size: 0.82rem;
                             color: #475569; cursor: pointer; transition: all 0.15s; }
    .report-toolbar button:hover { background: #f1f5f9; border-color: #94a3b8; }
    .report-toolbar button.copied { background: #ecfdf5; border-color: #a7f3d0; color: #065f46; }
    .report-placeholder { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: 1.25rem;
                         color: #1e40af; font-size: 0.95rem; line-height: 1.5; }
    .tax-report { font-family: 'Inter', system-ui, -apple-system, sans-serif; font-size: 0.92rem; color: #1e293b; }
    .tax-report .report-header { margin-bottom: 1rem; }
    .tax-report .report-main-title { font-size: 1.3rem; margin-bottom: 0.35rem; font-weight: 700;
                                     background: linear-gradient(135deg, #1a56db, #0ea5e9);
                                     -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .tax-report .report-meta { display: flex; flex-wrap: wrap; gap: 0.75rem; font-size: 0.88rem; color: #64748b; }
    .tax-report .report-section { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
                                  padding: 1.1rem 1.2rem; margin-bottom: 1rem;
                                  box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
    .tax-report .report-section-title { font-size: 1rem; margin: 0 0 0.65rem 0; color: #1e293b; font-weight: 600;
                                        padding-bottom: 0.4rem; border-bottom: 2px solid #e2e8f0; }
    .tax-report .report-row { display: flex; justify-content: space-between; align-items: baseline;
                              padding: 0.3rem 0; gap: 1rem; }
    .tax-report .report-row-total { font-weight: 600; border-top: 2px solid #e2e8f0; margin-top: 0.4rem; padding-top: 0.55rem; }
    .tax-report .report-row-highlight { font-weight: 700; font-size: 0.95rem; padding: 0.4rem 0; }
    .tax-report .report-row-refund { color: #16a34a; }
    .tax-report .report-row-refund .report-amount { color: #16a34a; }
    .tax-report .report-row-owed { color: #dc2626; }
    .tax-report .report-row-owed .report-amount { color: #dc2626; }
    .tax-report .report-label { flex: 1; }
    .tax-report .report-amount { flex-shrink: 0; font-variant-numeric: tabular-nums; font-weight: 600; }
    .tax-report .report-disclaimer { font-size: 0.8rem; color: #94a3b8; margin-top: 1rem; padding: 0.75rem;
                                     background: #f8fafc; border-radius: 8px; }

    /* Combined summary gradient */
    .tax-report .report-section:last-of-type { background: linear-gradient(135deg, #fafbff, #f0f4ff);
                                                border-color: #c7d2fe; }

    /* Dynamic field wrappers */
    .field-wrap { margin-top: 0.65rem; padding: 0.55rem 0.7rem; border-left: 3px solid #cbd5e1;
                  border-radius: 0 6px 6px 0; background: #f8fafc; }
    .field-wrap label:first-child { margin-top: 0; }

    /* Lender radio options */
    .lender-option { display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.7rem;
                     margin-top: 0.35rem; border: 1.5px solid #e2e8f0; border-radius: 8px; cursor: pointer;
                     transition: all 0.15s; }
    .lender-option:hover { background: #eff6ff; border-color: #93c5fd; }
    .lender-option.selected { background: #dbeafe; border-color: #3b82f6; }
    .lender-option input[type="radio"] { margin: 0; accent-color: #3b82f6; }
    .lender-detail { font-size: 0.9rem; }
    .lender-detail .lender-name { font-weight: 500; }
    .lender-detail .lender-amt { color: #64748b; font-size: 0.84rem; }
    .lender-none { display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.7rem;
                   margin-top: 0.35rem; border: 1.5px solid #e2e8f0; border-radius: 8px; cursor: pointer;
                   transition: all 0.15s; }
    .lender-none:hover { background: #eff6ff; border-color: #93c5fd; }
    .lender-none.selected { background: #dbeafe; border-color: #3b82f6; }

    /* YAML config upload */
    .yaml-upload { margin-top: 0.75rem; }
    .yaml-upload input[type="file"] { font-size: 0.88rem; }

    /* Print styles */
    @media print { .banner, .run-btn, .report-toolbar, .drop-zone, .step:not(#step3) { display: none !important; }
                   .step, .tax-report .report-section { box-shadow: none !important; break-inside: avoid; } }
  </style>
</head>
<body>
<div class="container">
  <div class="banner">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1a4.5 4.5 0 00-4.5 4.5V7H3a1 1 0 00-1 1v6a1 1 0 001 1h10a1 1 0 001-1V8a1 1 0 00-1-1h-.5V5.5A4.5 4.5 0 008 1zm0 1.5A3 3 0 0111 5.5V7H5V5.5A3 3 0 018 2.5z" fill="#2a7a2a"/></svg>
    <span>Everything runs locally. Your data and documents never leave your computer.</span>
  </div>

  <h1>Tax Return Tool</h1>
  <p class="subtitle">Calculate Federal (1040) and state taxes. State tax is calculated for California (Form 540) and New York (IT-201); other states show residency and W-2 withholding.</p>

  <form id="form">
    <!-- Step 1: Profile -->
    <div class="step">
      <div class="step-header">
        <span class="step-num">1</span>
        <span class="step-title">Your Profile</span>
      </div>
      <div class="field-row">
        <div>
          <label>Tax Year</label>
          <select name="tax_year" required>
            <option value="2024">2024</option>
            <option value="2025" selected>2025</option>
          </select>
        </div>
        <div>
          <label>Filing Status</label>
          <select name="filing_status" required id="filingStatus">
            <option value="single">Single</option>
            <option value="married_jointly">Married Filing Jointly</option>
            <option value="married_separately">Married Filing Separately</option>
            <option value="head_of_household">Head of Household</option>
          </select>
        </div>
      </div>
      <div class="field-row">
        <div>
          <label>Your name</label>
          <input type="text" name="taxpayer_name" placeholder="First Last">
        </div>
        <div>
          <label>SSN <span class="label-hint">- optional, for PDF forms</span></label>
          <input type="text" name="taxpayer_ssn" placeholder="123-45-6789" maxlength="11" autocomplete="off">
        </div>
      </div>
      <div class="field-row" id="spouseSsnRow" style="display:none">
        <div>
          <label>Spouse SSN <span class="label-hint">- optional, for PDF forms</span></label>
          <input type="text" name="spouse_ssn" placeholder="987-65-4321" maxlength="11" autocomplete="off">
        </div>
        <div></div>
      </div>
      <div class="field-row">
        <div style="max-width:100px">
          <label>Age</label>
          <input type="number" name="age" value="30" min="1" max="120">
        </div>
        <div>
          <label>State of residence</label>
          <select name="state_of_residence">
            {{ state_options | safe }}
          </select>
        </div>
      </div>
      <div class="checkbox-row">
        <label><input type="checkbox" name="is_renter"> Renter (for CA Renter's Credit)</label>
      </div>
    </div>

    <!-- Step 2: Documents -->
    <div class="step">
      <div class="step-header">
        <span class="step-num">2</span>
        <span class="step-title">Tax Documents</span>
      </div>
      <p class="hint" style="margin-bottom:0.3rem">Provide your W-2s, 1099s, 1098s, and other tax forms. Supported formats: PDF, CSV, Excel, and images.</p>
      <p class="hint" style="margin-bottom:0.5rem; color:#2a5a2a;"><strong>Read files on your device only</strong> — nothing is sent to the internet. Select or drop files/folders so this app can read them locally.</p>

      <label><strong>Read files</strong></label>
      <div class="drop-zone" id="dropZone">
        <div class="drop-zone-icon">&#128194;</div>
        <p>Drag and drop files or folders here to read them, or</p>
        <div class="browse-links">
          <button type="button" class="link-btn" id="selectFilesBtn">Browse files</button>
          <span style="color:#999">or</span>
          <button type="button" class="link-btn" id="selectFolderBtn">Select folder</button>
        </div>
        <p class="hint" style="margin-top:0.35rem; font-size:0.8rem;">Browser may ask for folder access — that is only to read files on your computer. Data stays on your device.</p>
        <p class="hint" style="margin-top:0.25rem; font-size:0.8rem; color:#2a5a2a;"><strong>If the browser shows &quot;Upload&quot;</strong> — that is the browser&apos;s wording only. You are <strong>not</strong> uploading to the internet; this app reads the files locally.</p>
        <input type="file" id="fileInput" multiple accept=".pdf,.csv,.xlsx,.xls,.jpg,.jpeg,.png,.tiff,.tif,.bmp" style="display:none">
        <input type="file" id="folderInput" webkitdirectory directory style="display:none">
        <div class="file-list" id="fileList"></div>
        <div class="file-count" id="fileCount" style="display:none"></div>
      </div>

    </div>

    <!-- Step 3: Additional Info (hidden until first run) -->
    <div class="step" id="step3" style="display:none">
      <div class="step-header">
        <span class="step-num">3</span>
        <span class="step-title">Additional Info</span>
      </div>
      <p class="hint" id="step3Hint">These items were not found in your documents. Fill in any that apply, then re-run.</p>

      <div class="field-wrap" data-field="charitable_contributions">
        <label>Charitable contributions <span class="label-hint">- cash donations (Schedule A)</span></label>
        <input type="number" name="charitable_contributions" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="primary_home_apn">
        <label>Which property is your primary home?</label>
        <p class="hint">Multiple properties found on your tax receipt. Select your primary residence; the rest will be treated as rental.</p>
        <div id="parcelOptions"></div>
        <input type="hidden" name="primary_home_apn" id="primaryApnHidden" value="">
      </div>
      <div class="field-wrap" data-field="primary_property_tax">
        <label>Primary home property tax paid</label>
        <input type="number" name="primary_property_tax" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="personal_mortgage_balance">
        <label>Primary home mortgage balance <span class="label-hint">- outstanding principal for $750K limit</span></label>
        <input type="number" name="personal_mortgage_balance" step="0.01" value="0">
        <p class="hint">Set to 0 if your balance is under $750K.</p>
      </div>
      <div class="field-wrap" data-field="federal_estimated_payments">
        <label>Federal estimated tax paid</label>
        <input type="number" name="federal_estimated_payments" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="ca_estimated_payments">
        <label>CA estimated tax paid</label>
        <input type="number" name="ca_estimated_payments" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="capital_loss_carryover">
        <label>Capital loss carryover from prior year <span class="label-hint">- applied up to $3,000/yr</span></label>
        <input type="number" name="capital_loss_carryover" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="short_term_loss_carryover">
        <label>Short-term loss carryover <span class="label-hint">- overrides single total above when set</span></label>
        <input type="number" name="short_term_loss_carryover" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="long_term_loss_carryover">
        <label>Long-term loss carryover</label>
        <input type="number" name="long_term_loss_carryover" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="pal_carryover">
        <label>PAL carryover <span class="label-hint">- prior-year passive activity loss (Form 8582)</span></label>
        <input type="number" name="pal_carryover" step="0.01" value="0">
      </div>
      <div class="field-wrap" data-field="rental_1098_keywords">
        <label>Which 1098 is for a rental property?</label>
        <p class="hint">Addresses below are from 1098 Box 8. Select the one that is your rental.</p>
        <div id="lenderOptions"></div>
        <input type="hidden" name="rental_1098_keywords" id="rental1098Hidden" value="">
      </div>

      <button type="button" class="toggle-btn" id="advancedToggle">
        <span class="toggle-arrow" id="advancedArrow">&#9654;</span>
        <span>All other overrides</span>
      </button>
      <div class="collapsible" id="advancedSection">
        <div class="field-group">
          <div class="field-group-title">Document Folder Path</div>
          <label>Scan a local folder instead <span class="label-hint">- scanned recursively</span></label>
          <input type="text" name="document_folder" placeholder="C:\\Users\\you\\Documents\\Tax2025">
        </div>
        <div class="field-group">
          <div class="field-group-title">Income Adjustments</div>
          <label>Other income <span class="label-hint">- 1099-MISC Box 3, jury duty, etc.</span></label>
          <input type="number" name="other_income" step="0.01" value="0">
          <label>Qualified dividends override <span class="label-hint">- 1099-DIV Box 1b total (if extraction is low)</span></label>
          <input type="number" name="qualified_dividends" step="0.01" value="0">
          <label>Ordinary dividends override <span class="label-hint">- 1099-DIV Box 1a total (if extraction is low)</span></label>
          <input type="number" name="ordinary_dividends" step="0.01" value="0">
          <label>US Treasury interest <span class="label-hint">- exempt from CA state tax</span></label>
          <input type="number" name="us_treasury_interest" step="0.01" value="0">
          <label>Federal withholding adjustment <span class="label-hint">- correction to auto-extracted amount</span></label>
          <input type="number" name="federal_withheld_adjustment" step="0.01" value="0">
        </div>
        <div class="field-group">
          <div class="field-group-title">California-specific</div>
          <label>CA miscellaneous deductions <span class="label-hint">- gross amount, before 2% AGI floor</span></label>
          <input type="number" name="ca_misc_deductions" step="0.01" value="0">
        </div>
        <div class="field-group">
          <div class="field-group-title">YAML Config</div>
          <p class="hint">Load a <code style="background:#eee;padding:0.1rem 0.3rem;border-radius:3px">tax_profile.yaml</code> to prefill all fields including rental properties and dependents.</p>
          <div class="yaml-upload">
            <input type="file" name="config_file" accept=".yaml,.yml">
          </div>
        </div>
      </div>
    </div>

    <button type="submit" class="run-btn" id="submitBtn">
      <span id="btnText">Calculate Taxes</span>
      <div class="spinner" id="spinner"></div>
    </button>
  </form>

  <div class="error-msg" id="message"></div>
  <div id="report"></div>
</div>

<div class="loading-overlay" id="loadingOverlay">
  <div class="overlay-spinner"></div>
  <div class="overlay-text">Calculating taxes...</div>
</div>

<script>
  const form = document.getElementById('form');
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const folderInput = document.getElementById('folderInput');
  const selectFilesBtn = document.getElementById('selectFilesBtn');
  const selectFolderBtn = document.getElementById('selectFolderBtn');
  const fileList = document.getElementById('fileList');
  const fileCount = document.getElementById('fileCount');
  const report = document.getElementById('report');
  const message = document.getElementById('message');
  const submitBtn = document.getElementById('submitBtn');
  const btnText = document.getElementById('btnText');
  const spinner = document.getElementById('spinner');
  const advancedToggle = document.getElementById('advancedToggle');
  const advancedSection = document.getElementById('advancedSection');
  const advancedArrow = document.getElementById('advancedArrow');
  const loadingOverlay = document.getElementById('loadingOverlay');

  /* Advanced toggle */
  advancedToggle.addEventListener('click', () => {
    advancedSection.classList.toggle('open');
    advancedArrow.classList.toggle('open');
  });

  /* Show/hide spouse SSN based on filing status */
  const filingStatus = document.getElementById('filingStatus');
  const spouseSsnRow = document.getElementById('spouseSsnRow');
  function updateSpouseRow() {
    const v = filingStatus.value;
    spouseSsnRow.style.display = (v === 'married_jointly' || v === 'married_separately') ? '' : 'none';
  }
  filingStatus.addEventListener('change', updateSpouseRow);
  updateSpouseRow();

  const droppedFiles = [];
  const ALLOWED_EXT = new Set(['.pdf','.csv','.xlsx','.xls','.jpg','.jpeg','.png','.tiff','.tif','.bmp']);

  /* File type icon helper */
  function fileIcon(name) {
    const ext = (name || '').toLowerCase().split('.').pop();
    if (ext === 'pdf') return '\\u{1F4C4}';
    if (['jpg','jpeg','png','tiff','tif','bmp'].includes(ext)) return '\\u{1F5BC}';
    if (['csv','xlsx','xls'].includes(ext)) return '\\u{1F4CA}';
    return '\\u{1F4CE}';
  }

  selectFilesBtn.addEventListener('click', (e) => { e.preventDefault(); fileInput.click(); });
  selectFolderBtn.addEventListener('click', (e) => { e.preventDefault(); folderInput.click(); });

  function allowedFile(file) {
    const n = (file.name || '').toLowerCase();
    const i = n.lastIndexOf('.');
    return i >= 0 && ALLOWED_EXT.has(n.slice(i));
  }
  function getAllFilesFromDataTransfer(dataTransfer) {
    return new Promise((resolve) => {
      const items = dataTransfer.items;
      if (!items || items.length === 0) {
        const raw = Array.from(dataTransfer.files || []);
        resolve(raw.filter(allowedFile));
        return;
      }
      const files = [];
      const getEntry = (item) => item.getAsEntry ? item.getAsEntry() : item.webkitGetAsEntry?.();
      let pending = 0;
      function done() {
        pending--;
        if (pending === 0) resolve(files);
      }
      function addFile(file) {
        if (allowedFile(file)) files.push(file);
      }
      function readDir(entry) {
        const reader = entry.createReader();
        pending++;
        function readBatch() {
          reader.readEntries((entries) => {
            for (const ent of entries || []) {
              if (ent.isFile) {
                pending++;
                ent.file((f) => { addFile(f); done(); });
              } else if (ent.isDirectory) readDir(ent);
            }
            if ((entries || []).length > 0) readBatch();
            else done();
          });
        }
        readBatch();
      }
      for (let i = 0; i < items.length; i++) {
        const entry = getEntry(items[i]);
        if (!entry) {
          const f = dataTransfer.files[i];
          if (f && allowedFile(f)) files.push(f);
          continue;
        }
        if (entry.isFile) {
          pending++;
          entry.file((f) => { addFile(f); done(); });
        } else if (entry.isDirectory) readDir(entry);
      }
      if (pending === 0) resolve(files);
    });
  }

  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const newFiles = await getAllFilesFromDataTransfer(e.dataTransfer);
    newFiles.forEach(f => droppedFiles.push(f));
    fileInput.files = new FileListFromArray(droppedFiles);
    renderFileList();
  });
  fileInput.addEventListener('change', () => {
    droppedFiles.length = 0;
    for (const f of fileInput.files) droppedFiles.push(f);
    renderFileList();
  });
  folderInput.addEventListener('change', () => {
    droppedFiles.length = 0;
    for (const f of folderInput.files) if (allowedFile(f)) droppedFiles.push(f);
    fileInput.files = new FileListFromArray(droppedFiles);
    renderFileList();
  });

  function FileListFromArray(files) {
    const dt = new DataTransfer();
    files.forEach(f => dt.items.add(f));
    return dt.files;
  }
  function clearFiles() {
    droppedFiles.length = 0;
    fileInput.value = '';
    renderFileList();
    submitBtn.classList.remove('pulse');
  }
  function renderFileList() {
    if (droppedFiles.length === 0) {
      fileList.innerHTML = '';
      fileCount.style.display = 'none';
      document.getElementById('fileClearBtn')?.remove();
      submitBtn.classList.remove('pulse');
      return;
    }
    fileList.innerHTML = droppedFiles.map(f =>
      '<div class="file-item"><span class="file-icon">' + fileIcon(f.name) + '</span><span class="file-name">' + f.name + '</span></div>'
    ).join('');
    /* File actions: count badge + clear button */
    let actionsEl = document.getElementById('fileActions');
    if (!actionsEl) {
      actionsEl = document.createElement('div');
      actionsEl.className = 'file-actions';
      actionsEl.id = 'fileActions';
      fileCount.parentNode.insertBefore(actionsEl, fileCount.nextSibling);
    }
    fileCount.textContent = droppedFiles.length + ' file' + (droppedFiles.length === 1 ? '' : 's');
    fileCount.style.display = 'inline-flex';
    fileCount.classList.remove('pop');
    void fileCount.offsetWidth;
    fileCount.classList.add('pop');
    actionsEl.innerHTML = '';
    actionsEl.appendChild(fileCount);
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button'; clearBtn.className = 'clear-btn'; clearBtn.textContent = 'Clear all';
    clearBtn.id = 'fileClearBtn';
    clearBtn.addEventListener('click', clearFiles);
    actionsEl.appendChild(clearBtn);
    /* Pulse CTA on calculate button */
    submitBtn.classList.add('pulse');
  }

  /* Input validation visual feedback */
  document.querySelectorAll('input[type="number"]').forEach(inp => {
    inp.addEventListener('input', () => {
      inp.classList.remove('input-valid', 'input-invalid');
      if (inp.value === '' || inp.value === '0') return;
      if (inp.validity.valid && !isNaN(parseFloat(inp.value))) {
        inp.classList.add('input-valid');
      } else {
        inp.classList.add('input-invalid');
      }
    });
  });

  const step3 = document.getElementById('step3');
  const step3Hint = document.getElementById('step3Hint');
  let hasRun = false;
  let plainTextReport = '';

  function showStep3(data) {
    const missing = data.missing || [];
    const allWraps = step3.querySelectorAll('.field-wrap[data-field]');
    // On first run, show only missing fields; on re-runs, keep all visible
    if (!hasRun) {
      const missingSet = new Set(missing);
      let anyVisible = false;
      allWraps.forEach(el => {
        if (missingSet.has(el.dataset.field)) {
          el.style.display = '';
          anyVisible = true;
        } else {
          el.style.display = 'none';
        }
      });
      if (anyVisible || missing.length > 0) {
        step3.style.display = '';
        step3.classList.add('step-fadein');
        step3Hint.textContent = 'These items were not found in your documents. Fill in any that apply, then re-run.';
      }
    }
    // Populate lender radio options if provided
    if (data.lender_options) {
      const container = document.getElementById('lenderOptions');
      const hidden = document.getElementById('rental1098Hidden');
      container.innerHTML = '';
      data.lender_options.forEach((opt, i) => {
        const label = document.createElement('label');
        label.className = 'lender-option';
        const radio = document.createElement('input');
        radio.type = 'radio'; radio.name = '_lender_pick'; radio.value = opt.lender;
        const detail = document.createElement('span');
        detail.className = 'lender-detail';
        const amt = Number(opt.interest).toLocaleString('en-US', {style:'currency', currency:'USD'});
        var primary = opt.display_label || opt.lender;
        detail.innerHTML = '<span class="lender-name">' + primary + '</span>'
          + ' <span class="lender-amt">' + String.fromCharCode(8211) + ' ' + amt + ' interest</span>';
        label.appendChild(radio);
        label.appendChild(detail);
        container.appendChild(label);
        radio.addEventListener('change', () => {
          hidden.value = opt.lender;
          container.querySelectorAll('.lender-option').forEach(l => l.classList.remove('selected'));
          label.classList.add('selected');
        });
      });
      // "None" option
      const noneLabel = document.createElement('label');
      noneLabel.className = 'lender-none';
      const noneRadio = document.createElement('input');
      noneRadio.type = 'radio'; noneRadio.name = '_lender_pick'; noneRadio.value = '';
      const noneText = document.createElement('span');
      noneText.className = 'lender-detail';
      noneText.innerHTML = '<span class="lender-name">None of these are rental</span>';
      noneLabel.appendChild(noneRadio);
      noneLabel.appendChild(noneText);
      container.appendChild(noneLabel);
      noneRadio.addEventListener('change', () => {
        hidden.value = '';
        container.querySelectorAll('.lender-option,.lender-none').forEach(l => l.classList.remove('selected'));
        noneLabel.classList.add('selected');
      });
    }
    // Populate parcel radio options if provided
    if (data.parcel_options) {
      const container = document.getElementById('parcelOptions');
      const hidden = document.getElementById('primaryApnHidden');
      container.innerHTML = '';
      data.parcel_options.forEach((opt, i) => {
        const label = document.createElement('label');
        label.className = 'lender-option';
        const radio = document.createElement('input');
        // Use address as the identifier when available, fall back to APN
        const id = opt.address || opt.apn;
        radio.type = 'radio'; radio.name = '_parcel_pick'; radio.value = id;
        const detail = document.createElement('span');
        detail.className = 'lender-detail';
        const amt = Number(opt.amount).toLocaleString('en-US', {style:'currency', currency:'USD'});
        const title = opt.address || ('APN: ' + opt.apn);
        detail.innerHTML = '<span class="lender-name">' + title + '</span>'
          + ' <span class="lender-amt">- ' + amt + '</span>';
        label.appendChild(radio);
        label.appendChild(detail);
        container.appendChild(label);
        radio.addEventListener('change', () => {
          hidden.value = id;
          container.querySelectorAll('.lender-option').forEach(l => l.classList.remove('selected'));
          label.classList.add('selected');
        });
      });
    }
    hasRun = true;
  }

  /* Report toolbar: copy + print */
  function addReportToolbar() {
    const existing = document.querySelector('.report-toolbar');
    if (existing) existing.remove();
    const toolbar = document.createElement('div');
    toolbar.className = 'report-toolbar';
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.innerHTML = '\\u{1F4CB} Copy';
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(plainTextReport).then(() => {
        copyBtn.classList.add('copied');
        copyBtn.innerHTML = '\\u2713 Copied';
        setTimeout(() => { copyBtn.classList.remove('copied'); copyBtn.innerHTML = '\\u{1F4CB} Copy'; }, 2000);
      });
    });
    const printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.innerHTML = '\\u{1F5A8} Print';
    printBtn.addEventListener('click', () => window.print());
    toolbar.appendChild(copyBtn);
    toolbar.appendChild(printBtn);
    report.insertBefore(toolbar, report.firstChild);
  }

  /* Disable/enable all form inputs */
  function setFormDisabled(disabled) {
    form.querySelectorAll('input, select, button').forEach(el => {
      if (el.id === 'submitBtn') return;
      el.disabled = disabled;
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    message.textContent = '';
    report.innerHTML = '';
    btnText.textContent = 'Calculating...';
    spinner.style.display = 'block';
    submitBtn.disabled = true;
    submitBtn.classList.remove('pulse');
    loadingOverlay.classList.add('active');
    setFormDisabled(true);
    const fd = new FormData(form);
    for (const f of droppedFiles) fd.append('documents', f);
    try {
      const r = await fetch('/run', { method: 'POST', body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        message.textContent = data.error || r.statusText || 'Request failed';
      } else {
        var missing = data.missing || [];
        plainTextReport = data.report || '';
        var isFirstRun = !hasRun;
        showStep3(data);
        /* First run with missing fields: show only Step 3, hide report */
        if (isFirstRun && missing.length > 0) {
          report.innerHTML = '';
          step3.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          report.innerHTML = data.report_html || '';
          if (!report.innerHTML && data.report) report.textContent = data.report;
          if (report.innerHTML) {
            report.classList.add('report-fadein');
            addReportToolbar();
            setTimeout(() => report.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
          }
        }
      }
    } catch (err) {
      message.textContent = err.message || 'Network error';
    }
    loadingOverlay.classList.remove('active');
    setFormDisabled(false);
    btnText.textContent = 'Calculate Taxes';
    spinner.style.display = 'none';
    submitBtn.disabled = false;
  });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
