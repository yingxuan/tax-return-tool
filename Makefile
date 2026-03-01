.PHONY: install web demo test

## One-command setup: installs Tesseract OCR + all Python dependencies
install:
	@echo "==> Installing Python dependencies..."
	pip install -r requirements.txt
	@echo ""
	@OS=$$(uname -s 2>/dev/null); \
	if [ "$$OS" = "Darwin" ]; then \
		echo "==> Installing Tesseract OCR via Homebrew..."; \
		brew install tesseract; \
	elif [ "$$OS" = "Linux" ]; then \
		echo "==> Installing Tesseract OCR via apt..."; \
		sudo apt-get install -y tesseract-ocr; \
	else \
		echo ""; \
		echo "==> Windows detected."; \
		echo "    Tesseract must be installed manually:"; \
		echo "    https://github.com/UB-Mannheim/tesseract/wiki"; \
		echo "    (Python packages above have been installed.)"; \
	fi
	@echo ""
	@echo "Done. Run 'make web' to launch the browser UI."

## Launch the web UI at http://localhost:5000
web:
	python -m src.ui_app

## Run with built-in demo data (no documents needed)
demo:
	python -m src.main --demo

## Run the test suite
test:
	python test_tax_calculation.py
