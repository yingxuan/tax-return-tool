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
        filing_status=filing_status,
        age=_int(form, "age", 30),
        state_of_residence=state_of_residence,
        is_ca_resident=(state_of_residence == "CA"),
        is_renter=form.get("is_renter") in ("true", "1", "on", "yes"),
        dependents=[],
        document_folder=document_folder,
        rental_1098_keywords=rental_1098_keywords,
        capital_loss_carryover=_float(form, "capital_loss_carryover"),
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
    body { font-family: system-ui, -apple-system, sans-serif; background: #f5f7fa; color: #1a1a1a; }
    .container { max-width: 760px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    .subtitle { color: #555; margin-bottom: 1.5rem; font-size: 0.95rem; }

    /* Privacy banner */
    .banner { display: flex; align-items: flex-start; gap: 0.5rem; background: #eef6ee; border: 1px solid #b6d7b6;
              border-radius: 8px; padding: 0.6rem 0.85rem; margin-bottom: 1.25rem; font-size: 0.88rem; color: #2a5a2a; }
    .banner svg { flex-shrink: 0; margin-top: 2px; }

    /* Steps */
    .step { background: #fff; border: 1px solid #dde1e6; border-radius: 10px; padding: 1.25rem 1.25rem 1rem;
            margin-bottom: 1rem; }
    .step-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
    .step-num { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
                border-radius: 50%; background: #0066cc; color: #fff; font-size: 0.85rem; font-weight: 600;
                flex-shrink: 0; }
    .step-title { font-size: 1.05rem; font-weight: 600; }

    /* Form fields */
    label { display: block; margin-top: 0.75rem; font-weight: 500; font-size: 0.92rem; }
    label:first-child { margin-top: 0; }
    .label-hint { font-weight: 400; color: #666; font-size: 0.84rem; }
    input[type="text"], input[type="number"], select {
      width: 100%; padding: 0.45rem 0.55rem; margin-top: 0.2rem; border: 1px solid #ccc;
      border-radius: 6px; font-size: 0.92rem; background: #fff; }
    input[type="text"]:focus, input[type="number"]:focus, select:focus {
      outline: none; border-color: #0066cc; box-shadow: 0 0 0 2px rgba(0,102,204,0.15); }
    .field-row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    .field-row > * { flex: 1; min-width: 140px; }
    .checkbox-row { display: flex; gap: 1.25rem; align-items: center; margin-top: 0.75rem; }
    .checkbox-row label { margin-top: 0; font-weight: 400; cursor: pointer; display: flex; align-items: center; gap: 0.35rem; }
    .hint { font-size: 0.82rem; color: #777; margin-top: 0.2rem; line-height: 1.3; }

    /* Drop zone */
    .drop-zone {
      border: 2px dashed #b0b8c4; border-radius: 10px; padding: 1.5rem; text-align: center;
      margin-top: 0.75rem; background: #fafbfc; transition: all 0.15s; cursor: pointer; }
    .drop-zone:hover { border-color: #0066cc; background: #f0f6ff; }
    .drop-zone.dragover { border-color: #0066cc; background: #e0edff; border-style: solid; }
    .drop-zone-icon { font-size: 1.8rem; margin-bottom: 0.3rem; color: #888; }
    .drop-zone p { margin: 0.25rem 0; color: #555; font-size: 0.9rem; }
    .drop-zone .browse-links { margin-top: 0.5rem; }
    .link-btn { background: none; border: none; color: #0066cc; cursor: pointer; padding: 0.2rem 0.4rem;
                font-size: 0.9rem; text-decoration: underline; font-weight: 500; }
    .link-btn:hover { color: #004499; }
    .file-list { font-size: 0.85rem; color: #333; text-align: left; max-height: 120px; overflow: auto;
                 margin-top: 0.5rem; padding: 0 0.5rem; }
    .file-count { display: inline-block; background: #e0edff; color: #0055aa; font-size: 0.82rem;
                  padding: 0.15rem 0.55rem; border-radius: 12px; margin-top: 0.4rem; font-weight: 500; }
    .or-divider { display: flex; align-items: center; gap: 0.75rem; margin: 0.9rem 0; color: #999; font-size: 0.85rem; }
    .or-divider::before, .or-divider::after { content: ""; flex: 1; border-top: 1px solid #ddd; }

    /* Collapsible advanced */
    .toggle-btn { background: none; border: 1px solid #dde1e6; border-radius: 8px; padding: 0.5rem 0.85rem;
                  cursor: pointer; font-size: 0.9rem; color: #444; display: flex; align-items: center;
                  gap: 0.4rem; margin-top: 0.75rem; width: 100%; }
    .toggle-btn:hover { background: #f5f7fa; border-color: #bbb; }
    .toggle-arrow { transition: transform 0.2s; font-size: 0.75rem; }
    .toggle-arrow.open { transform: rotate(90deg); }
    .collapsible { display: none; margin-top: 0.5rem; }
    .collapsible.open { display: block; }
    .field-group { border-left: 3px solid #e0e4e8; padding-left: 0.85rem; margin-top: 0.75rem; }
    .field-group-title { font-size: 0.82rem; font-weight: 600; color: #777; text-transform: uppercase;
                         letter-spacing: 0.04em; margin-bottom: 0.25rem; }

    /* Run button */
    .run-btn { display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%;
               padding: 0.75rem; margin-top: 1.25rem; cursor: pointer; background: #0066cc; color: #fff;
               border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; transition: background 0.15s; }
    .run-btn:hover { background: #0055aa; }
    .run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .spinner { display: none; width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.3);
               border-top-color: #fff; border-radius: 50%; animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Report */
    .error-msg { color: #c00; margin-top: 0.75rem; font-size: 0.9rem; padding: 0.5rem 0.75rem;
                 background: #fff0f0; border-radius: 6px; border: 1px solid #fcc; }
    .error-msg:empty { display: none; }
    #report { margin-top: 1rem; max-height: 70vh; overflow: auto; }
    #report:empty { display: none; }
    .report-placeholder { background: #f0f4ff; border: 1px solid #99b8e8; border-radius: 10px; padding: 1.25rem;
                         color: #1a3a5c; font-size: 0.95rem; line-height: 1.5; }
    .tax-report { font-family: system-ui, -apple-system, sans-serif; font-size: 0.92rem; color: #1a1a1a; }
    .tax-report .report-header { margin-bottom: 1rem; }
    .tax-report .report-main-title { font-size: 1.25rem; margin-bottom: 0.35rem; color: #0066cc; }
    .tax-report .report-meta { display: flex; flex-wrap: wrap; gap: 0.75rem; font-size: 0.88rem; color: #555; }
    .tax-report .report-section { background: #fff; border: 1px solid #e0e4e8; border-radius: 8px;
                                  padding: 1rem 1.15rem; margin-bottom: 1rem; }
    .tax-report .report-section-title { font-size: 1rem; margin: 0 0 0.65rem 0; color: #333;
                                        padding-bottom: 0.35rem; border-bottom: 1px solid #e0e4e8; }
    .tax-report .report-row { display: flex; justify-content: space-between; align-items: baseline;
                              padding: 0.25rem 0; gap: 1rem; }
    .tax-report .report-row-total { font-weight: 600; border-top: 1px solid #e0e4e8; margin-top: 0.35rem; padding-top: 0.5rem; }
    .tax-report .report-row-highlight { font-weight: 700; color: #0066cc; }
    .tax-report .report-label { flex: 1; }
    .tax-report .report-amount { flex-shrink: 0; font-variant-numeric: tabular-nums; }
    .tax-report .report-disclaimer { font-size: 0.8rem; color: #777; margin-top: 1rem; }

    /* Dynamic field wrappers */
    .field-wrap { margin-top: 0.65rem; padding: 0.5rem 0.65rem; border-left: 3px solid #e0e4e8; }
    .field-wrap label:first-child { margin-top: 0; }

    /* Lender radio options */
    .lender-option { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.65rem;
                     margin-top: 0.35rem; border: 1px solid #dde1e6; border-radius: 6px; cursor: pointer; }
    .lender-option:hover { background: #f0f4ff; border-color: #99b8e8; }
    .lender-option.selected { background: #e8f0fe; border-color: #0066cc; }
    .lender-option input[type="radio"] { margin: 0; }
    .lender-detail { font-size: 0.9rem; }
    .lender-detail .lender-name { font-weight: 500; }
    .lender-detail .lender-amt { color: #555; font-size: 0.84rem; }
    .lender-none { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.65rem;
                   margin-top: 0.35rem; border: 1px solid #dde1e6; border-radius: 6px; cursor: pointer; }
    .lender-none:hover { background: #f0f4ff; border-color: #99b8e8; }
    .lender-none.selected { background: #e8f0fe; border-color: #0066cc; }

    /* YAML config upload */
    .yaml-upload { margin-top: 0.75rem; }
    .yaml-upload input[type="file"] { font-size: 0.88rem; }
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
          <select name="filing_status" required>
            <option value="single">Single</option>
            <option value="married_jointly">Married Filing Jointly</option>
            <option value="married_separately">Married Filing Separately</option>
            <option value="head_of_household">Head of Household</option>
          </select>
        </div>
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

  /* Advanced toggle */
  advancedToggle.addEventListener('click', () => {
    advancedSection.classList.toggle('open');
    advancedArrow.classList.toggle('open');
  });

  const droppedFiles = [];
  const ALLOWED_EXT = new Set(['.pdf','.csv','.xlsx','.xls','.jpg','.jpeg','.png','.tiff','.tif','.bmp']);

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
  function renderFileList() {
    if (droppedFiles.length === 0) {
      fileList.textContent = '';
      fileCount.style.display = 'none';
      return;
    }
    fileList.textContent = droppedFiles.map(f => f.name).join('\\n');
    fileCount.textContent = droppedFiles.length + ' file' + (droppedFiles.length === 1 ? '' : 's') + ' selected';
    fileCount.style.display = 'inline-block';
  }

  const step3 = document.getElementById('step3');
  const step3Hint = document.getElementById('step3Hint');
  let hasRun = false;

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
          + ' <span class="lender-amt">– ' + amt + ' interest</span>';
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

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    message.textContent = '';
    report.innerHTML = '';
    btnText.textContent = 'Calculating...';
    spinner.style.display = 'block';
    submitBtn.disabled = true;
    const fd = new FormData(form);
    for (const f of droppedFiles) fd.append('documents', f);
    try {
      const r = await fetch('/run', { method: 'POST', body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        message.textContent = data.error || r.statusText || 'Request failed';
      } else {
        var missing = data.missing || [];
        report.innerHTML = data.report_html || '';
        if (!report.innerHTML && data.report) report.textContent = data.report;
        if (missing.length > 0 && report.innerHTML) {
          var placeholder = document.createElement('p');
          placeholder.className = 'report-placeholder';
          placeholder.innerHTML = 'Some items were not found in your documents. You can fill them in below and click <strong>Calculate Taxes</strong> again to update the summary.';
          report.insertBefore(placeholder, report.firstChild);
        }
        showStep3(data);
        if (!hasRun && missing.length > 0) step3.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    } catch (err) {
      message.textContent = err.message || 'Network error';
    }
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
