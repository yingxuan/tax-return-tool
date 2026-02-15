"""Simple Web UI for the tax return tool.

Provides manual input, folder path, and file upload/drag-drop; calls existing
process_tax_documents / process_tax_return / generate_full_report without
changing core logic.
"""

import os
import shutil
import tempfile
from pathlib import Path

from flask import Flask, request, render_template_string, jsonify

# Import existing pipeline; no changes to these modules
from .config_loader import load_config, TaxProfileConfig
from .main import process_tax_documents, process_tax_return
from .report_generator import generate_full_report

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
    keywords_str = (form.get("rental_1098_keywords") or "").strip()
    rental_1098_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    return TaxProfileConfig(
        tax_year=_int(form, "tax_year", 2025),
        taxpayer_name=(form.get("taxpayer_name") or "Taxpayer").strip(),
        filing_status=filing_status,
        age=_int(form, "age", 30),
        is_ca_resident=form.get("is_ca_resident") in ("true", "1", "on", "yes"),
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
        primary_property_tax=_float(form, "primary_property_tax"),
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
    config.is_ca_resident = form.get("is_ca_resident") in ("true", "1", "on", "yes")
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
    config.primary_property_tax = _float(form, "primary_property_tax", config.primary_property_tax)
    return config


@app.route("/")
def index():
    """Serve the single-page UI."""
    return render_template_string(INDEX_HTML)


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

        tax_return = process_tax_return(tax_return)
        report = generate_full_report(tax_return)
        return jsonify({"report": report})

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
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 0 auto; padding: 1rem; }
    h1 { margin-top: 0; }
    label { display: block; margin-top: 0.6rem; font-weight: 500; }
    input[type="text"], input[type="number"], select { width: 100%; padding: 0.4rem; margin-top: 0.2rem; }
    .row { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    .row label { margin-top: 0; }
    .drop-zone {
      border: 2px dashed #888; border-radius: 8px; padding: 1.5rem; text-align: center; margin: 1rem 0;
      background: #f8f8f8;
    }
    .drop-zone.dragover { border-color: #06c; background: #e8f0fe; }
    .drop-zone p { margin: 0 0 0.5rem 0; color: #555; }
    .file-list { font-size: 0.9rem; color: #333; text-align: left; max-height: 120px; overflow: auto; }
    button { padding: 0.6rem 1.2rem; margin-top: 1rem; cursor: pointer; background: #06c; color: #fff; border: none; border-radius: 6px; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    #report { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.85rem; background: #f5f5f5; padding: 1rem; border-radius: 6px; margin-top: 1rem; max-height: 60vh; overflow: auto; }
    .error { color: #c00; margin-top: 0.5rem; }
    section { margin-bottom: 1.2rem; }
    .hint { font-size: 0.85rem; color: #666; margin-top: 0.2rem; }
    .link-row { margin: 0.4rem 0; }
    .link-btn { background: none; border: none; color: #06c; cursor: pointer; padding: 0; font-size: inherit; text-decoration: underline; }
    .link-btn:hover { color: #004; }
    .disclaimer { font-size: 0.9rem; color: #555; background: #f0f4f8; border: 1px solid #c8d4e0; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 1rem; }
    .disclaimer code { font-family: ui-monospace, monospace; background: #e0e6ec; padding: 0.15rem 0.4rem; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="disclaimer">All information you enter and all documents you upload stay on your device. Nothing is sent to any external server.</div>
  <div class="disclaimer">You must install all dependencies before using this tool. From the project root run: <code>pip install -r requirements.txt</code>. This installs Flask (Web UI), PyYAML (config), pdfplumber/Pillow/pytesseract (PDF and image parsing), and pandas/openpyxl (data).</div>
  <h1>Tax Return Tool</h1>
  <p>Enter profile and either a document folder path or drag-and-drop files, then run.</p>

  <form id="form">
    <section>
      <h2>Profile</h2>
      <label>Tax year</label>
      <select name="tax_year" required>
        <option value="2024">2024</option>
        <option value="2025" selected>2025</option>
      </select>
      <label>Filing status</label>
      <select name="filing_status" required>
        <option value="single">Single</option>
        <option value="married_jointly">Married Filing Jointly</option>
        <option value="married_separately">Married Filing Separately</option>
        <option value="head_of_household">Head of Household</option>
      </select>
      <label>Taxpayer name</label>
      <input type="text" name="taxpayer_name" value="Taxpayer" placeholder="e.g. John & Jane">
      <label>Age</label>
      <input type="number" name="age" value="30" min="1" max="120">
      <div class="row">
        <label><input type="checkbox" name="is_ca_resident" checked> CA resident</label>
        <label><input type="checkbox" name="is_renter"> Renter</label>
      </div>
    </section>

    <section>
      <h2>Document source</h2>
      <label>Document folder path (if not using file upload)</label>
      <input type="text" name="document_folder" placeholder="C:\\Users\\...\\tax2025\\2024">
      <p class="hint">Paste the full path to the folder containing PDF/CSV/images. Leave empty if using drag-and-drop below.</p>

      <label>Or drag-and-drop files or folders here</label>
      <div class="drop-zone" id="dropZone">
        <p>Drop files or folders (PDF, CSV, images) here, or</p>
        <p class="link-row">
          <button type="button" class="link-btn" id="selectFilesBtn">Select files</button>
          <span> </span>
          <button type="button" class="link-btn" id="selectFolderBtn">Select folder</button>
        </p>
        <input type="file" id="fileInput" multiple accept=".pdf,.csv,.xlsx,.xls,.jpg,.jpeg,.png,.tiff,.tif,.bmp" style="display:none">
        <input type="file" id="folderInput" webkitdirectory directory style="display:none">
        <div class="file-list" id="fileList"></div>
      </div>
    </section>

    <section>
      <h2>Optional: Load config from YAML</h2>
      <label>Upload tax_profile.yaml to prefill (rentals, dependents, etc.)</label>
      <input type="file" name="config_file" accept=".yaml,.yml">
    </section>

    <section>
      <h2>Overrides (optional)</h2>
      <label>Primary Home property tax paid</label>
      <input type="number" name="primary_property_tax" step="0.01" value="0" placeholder="0">
      <label>Capital loss carryover from 2024</label>
      <input type="number" name="capital_loss_carryover" step="0.01" value="0" placeholder="0">
      <label>Primary Home mortgage balance</label>
      <input type="number" name="personal_mortgage_balance" step="0.01" value="0" placeholder="0">
      <label>Charitable contributions</label>
      <input type="number" name="charitable_contributions" step="0.01" value="0" placeholder="0">
      <label>Estimated tax paid to Federal</label>
      <input type="number" name="federal_estimated_payments" step="0.01" value="0" placeholder="0">
      <label>Estimated tax paid to CA</label>
      <input type="number" name="ca_estimated_payments" step="0.01" value="0" placeholder="0">
      <label>Keyword of rental home address (to differentiate 1098 forms for Primary vs Rental properties)</label>
      <input type="text" name="rental_1098_keywords" placeholder="e.g. hiawatha">
    </section>

    <button type="submit" id="submitBtn">Run</button>
  </form>

  <div id="message" class="error"></div>
  <pre id="report"></pre>

  <script>
    const form = document.getElementById('form');
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const folderInput = document.getElementById('folderInput');
    const selectFilesBtn = document.getElementById('selectFilesBtn');
    const selectFolderBtn = document.getElementById('selectFolderBtn');
    const fileList = document.getElementById('fileList');
    const report = document.getElementById('report');
    const message = document.getElementById('message');
    const submitBtn = document.getElementById('submitBtn');

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
      fileList.textContent = droppedFiles.length ? droppedFiles.map(f => f.name).join('\\n') : '';
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      message.textContent = '';
      report.textContent = 'Running...';
      submitBtn.disabled = true;
      const fd = new FormData(form);
      for (const f of droppedFiles) fd.append('documents', f);
      try {
        const r = await fetch('/run', { method: 'POST', body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          message.textContent = data.error || r.statusText || 'Request failed';
          report.textContent = '';
        } else {
          report.textContent = data.report || '';
        }
      } catch (err) {
        message.textContent = err.message || 'Network error';
        report.textContent = '';
      }
      submitBtn.disabled = false;
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
