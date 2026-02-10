"""Extract structured tax data from parsed documents."""

import re
from typing import Optional, List, Tuple
from dataclasses import dataclass

from .document_parser import ParsedDocument
from .models import (
    W2Data, Form1099Int, Form1099Div, Form1099Misc, Form1099Nec,
    Form1099R, Form1099B, Form1099G, Form1098, Form1098T,
)


@dataclass
class ExtractionResult:
    """Result of data extraction attempt."""
    success: bool
    form_type: Optional[str]
    data: Optional[object]
    confidence: float
    warnings: List[str]


class TaxDataExtractor:
    """Extract tax form data from parsed documents."""

    # W-2 box labels and their patterns
    W2_PATTERNS = {
        'employer_name': [
            r"Employer.?s?\s*name[^A-Z]*([A-Z][A-Za-z\s&.,]+(?:CORPORATION|CORP|INC|LLC|COMPANY|CO)?)",
            r"(?:employer'?s?\s+name|employer\s+information)[:\s]*([A-Z][A-Za-z\s&.,]+)",
            r"^([A-Z][A-Za-z\s&.,]+(?:Inc|LLC|Corp|Company|Co)\.?)",
        ],
        'employer_ein': [
            r"(?:employer.?s?\s*FED\s*ID|employer\s+identification\s+number|ein)[^\d]*(\d{2}-?\d{7})",
        ],
        'wages': [
            # Look for the pattern: wages value followed by federal withheld value on same/next line
            r"([\d,]+\.?\d{2})\s+[\d,]+\.?\d{2}\s*\n.*?3\s*Social",  # value before Box 2 value
            r"1\s+Wages.*?\n\s*([\d,]+\.?\d{2})",  # value on next line after label
            r"Box\s*1[:\s]*([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            # Second number in the pair
            r"[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})\s*\n.*?3\s*Social",
            r"2\s+Federal.*?\n\s*[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})",
            r"Box\s*2[:\s]*([\d,]+\.?\d*)",
        ],
        'social_security_wages': [
            r"3\s+Social.*?wages.*?\n\s*([\d,]+\.?\d{2})",
            r"(?:box\s*3|social\s+security\s+wages)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'social_security_tax': [
            r"4\s+Social.*?tax.*?\n\s*[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})",
            r"(?:box\s*4|social\s+security\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'medicare_wages': [
            r"5\s+Medicare.*?wages.*?\n\s*([\d,]+\.?\d{2})",
            r"(?:box\s*5|medicare\s+wages)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'medicare_tax': [
            r"6\s+Medicare.*?tax.*?\n\s*[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})",
            r"(?:box\s*6|medicare\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'state': [
            r"\n([A-Z]{2})\s+[\d-]+\s+\d?\s*[\d,]+\.?\d{2}",
            r"15\s*State.*?([A-Z]{2})\b",
        ],
        'state_wages': [
            r"16\s+State.*?\n.*?([A-Z]{2})\s+[\d-]+\s+\d?\s*([\d,]+\.?\d{2})",
            r"(?:box\s*16|state\s+wages)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'state_withheld': [
            r"17\s+State.*?income.*?tax.*?\n\s*([\d,]+\.?\d{2})",
            r"State\s+income\s+tax\s+([\d,]+\.?\d{2})",
            r"(?:box\s*17|state\s+income\s+tax)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # 1099-INT patterns
    FORM_1099_INT_PATTERNS = {
        'payer_name': [
            r"(?:payer'?s?\s+name)[:\s]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'interest_income': [
            r"(?:box\s*1|interest\s+income)[:\s]*\$?([\d,]+\.?\d*)",
            r"1\s+Interest\s+income[^$]*\$?([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            r"(?:box\s*4|federal\s+income\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # 1099-DIV patterns
    FORM_1099_DIV_PATTERNS = {
        'payer_name': [
            r"(?:payer'?s?\s+name)[:\s]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'ordinary_dividends': [
            r"(?:box\s*1a|total\s+ordinary\s+dividends)[:\s]*\$?([\d,]+\.?\d*)",
            r"1a\s+Total\s+ordinary\s+dividends[^$]*\$?([\d,]+\.?\d*)",
        ],
        'qualified_dividends': [
            r"(?:box\s*1b|qualified\s+dividends)[:\s]*\$?([\d,]+\.?\d*)",
            r"1b\s+Qualified\s+dividends[^$]*\$?([\d,]+\.?\d*)",
        ],
        'capital_gain_distributions': [
            r"(?:box\s*2a|total\s+capital\s+gain)[:\s]*\$?([\d,]+\.?\d*)",
            r"2a\s+Total\s+capital\s+gain[^$]*\$?([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            r"(?:box\s*4|federal\s+income\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # 1099-NEC patterns
    FORM_1099_NEC_PATTERNS = {
        'payer_name': [
            r"(?:payer'?s?\s+name)[:\s]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'nonemployee_compensation': [
            r"(?:box\s*1|nonemployee\s+compensation)[:\s]*\$?([\d,]+\.?\d*)",
            r"1\s+Nonemployee\s+compensation[^$]*\$?([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            r"(?:box\s*4|federal\s+income\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # 1099-R patterns (retirement distributions)
    # Real 1099-R PDFs put dollar values on a different line from the label,
    # so patterns must allow matching across newlines.
    FORM_1099_R_PATTERNS = {
        'payer_name': [
            r"PAYER.?S\s+name,\s*street[^\n]*\n([A-Z][A-Za-z\s&.,]+)",
            r"(?:payer'?s?\s+name)[:\s]*([A-Z][A-Za-z\s&.,]+)",
            r"PAYER.?S\s+NAME[^A-Z]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'gross_distribution': [
            r"\$\s*([\d,]+\.\d{2})\s*(?:Retirement|$)",
            r"1\s*Gross\s*distribution[\s\S]{0,80}\$([\d,]+\.\d{2})",
            r"Gross\s*distribution[\s\S]{0,80}\$([\d,]+\.\d{2})",
            r"(?:box\s*1|gross\s+distribution)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'taxable_amount': [
            r"2a\s*Taxable\s*amount[\s\S]{0,80}\$([\d,]+\.\d{2})",
            r"Taxable\s*amount[\s\S]{0,40}\$([\d,]+\.\d{2})",
            r"(?:box\s*2a|taxable\s+amount)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            r"4\s*Federal\s*income\s*tax\s*withheld[\s\S]{0,80}\$([\d,]+\.\d{2})",
            r"Federal\s*income\s*tax\s*withheld[\s\S]{0,40}\$([\d,]+\.\d{2})",
            r"(?:box\s*4|federal\s+income\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'state_withheld': [
            r"14\s*State\s*tax\s*withheld[\s\S]{0,40}\$([\d,]+\.\d{2})",
            r"State\s*tax\s*withheld[\s\S]{0,40}\$([\d,]+\.\d{2})",
        ],
    }

    # 1098 patterns (mortgage interest)
    FORM_1098_PATTERNS = {
        'lender_name': [
            r"RECIPIENT.?S/LENDER.?S\s+name[^A-Z]*\n([A-Z][A-Za-z\s&.,]+)",
            r"(?:recipient|lender).?s?\s*name[^A-Z]*([A-Z][A-Za-z\s&.,]+)",
            r"RECIPIENT.?S\s+NAME[^A-Z]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'mortgage_interest': [
            r"1\s*Mortgage\s*interest\s*(?:received)?[^$]*\$([\d,]+\.\d{2})",
            r"Mortgage\s*interest\s*(?:received\s*from)?[^$]*\$([\d,]+\.\d{2})",
            r"(?:box\s*1|mortgage\s+interest)[:\s]*\$?([\d,]+\.?\d+)",
        ],
        'property_taxes': [
            r"Real\s*[Ee]state\s*[Tt]axes?\s*[Pp]aid\s*(?:in\s*\d{4})?\s*\$([\d,]+\.\d{2})",
            r"10\s*(?:Real\s*estate|Property)\s*taxes?[^$]*\$([\d,]+\.\d{2})",
            r"(?:box\s*10|property\s+taxes?)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    def __init__(self):
        """Initialize the tax data extractor."""
        pass

    def _extract_from_csv(self, document: ParsedDocument) -> Optional[ExtractionResult]:
        """
        Extract data from CSV/spreadsheet documents.

        Args:
            document: Parsed document with raw_data DataFrame

        Returns:
            ExtractionResult if successful, None otherwise
        """
        if document.raw_data is None:
            return None

        df = document.raw_data

        # Check if it's a key-value format (2 columns)
        if len(df.columns) == 2:
            # Convert to dictionary
            data_dict = {}
            for _, row in df.iterrows():
                key = str(row.iloc[0]).lower().strip()
                value = str(row.iloc[1]).strip()
                data_dict[key] = value

            # Identify form type
            form_type = data_dict.get('form type', '').upper()

            if 'W-2' in form_type or 'W2' in form_type:
                return self._extract_w2_from_dict(data_dict)
            elif '1099-INT' in form_type:
                return self._extract_1099_int_from_dict(data_dict)
            elif '1099-DIV' in form_type:
                return self._extract_1099_div_from_dict(data_dict)
            elif '1099-NEC' in form_type:
                return self._extract_1099_nec_from_dict(data_dict)

        return None

    def _parse_csv_amount(self, value: str) -> float:
        """Parse amount from CSV value."""
        try:
            clean = value.replace(',', '').replace('$', '').strip()
            return float(clean)
        except (ValueError, AttributeError):
            return 0.0

    def _extract_w2_from_dict(self, data: dict) -> ExtractionResult:
        """Extract W-2 data from key-value dictionary."""
        employer = data.get('employer name', 'Unknown Employer')
        wages = self._parse_csv_amount(data.get('box 1 wages', '0'))
        fed_withheld = self._parse_csv_amount(data.get('box 2 federal income tax withheld', '0'))
        ss_wages = self._parse_csv_amount(data.get('box 3 social security wages', '0'))
        ss_tax = self._parse_csv_amount(data.get('box 4 social security tax withheld', '0'))
        medicare_wages = self._parse_csv_amount(data.get('box 5 medicare wages', '0'))
        medicare_tax = self._parse_csv_amount(data.get('box 6 medicare tax withheld', '0'))
        state = data.get('box 15 state', '')
        state_wages = self._parse_csv_amount(data.get('box 16 state wages', '0'))
        state_withheld = self._parse_csv_amount(data.get('box 17 state income tax', '0'))

        w2_data = W2Data(
            employer_name=employer,
            wages=wages,
            federal_withheld=fed_withheld,
            social_security_wages=ss_wages,
            social_security_tax=ss_tax,
            medicare_wages=medicare_wages,
            medicare_tax=medicare_tax,
            state=state if state else None,
            state_wages=state_wages,
            state_withheld=state_withheld
        )

        return ExtractionResult(
            success=wages > 0,
            form_type='W-2',
            data=w2_data,
            confidence=1.0,
            warnings=[]
        )

    def _extract_1099_int_from_dict(self, data: dict) -> ExtractionResult:
        """Extract 1099-INT data from key-value dictionary."""
        payer = data.get('payer name', 'Unknown Payer')
        interest = self._parse_csv_amount(data.get('box 1 interest income', '0'))
        fed_withheld = self._parse_csv_amount(data.get('box 4 federal income tax withheld', '0'))

        form_data = Form1099Int(
            payer_name=payer,
            interest_income=interest,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=interest > 0,
            form_type='1099-INT',
            data=form_data,
            confidence=1.0,
            warnings=[]
        )

    def _extract_1099_div_from_dict(self, data: dict) -> ExtractionResult:
        """Extract 1099-DIV data from key-value dictionary."""
        payer = data.get('payer name', 'Unknown Payer')
        ordinary = self._parse_csv_amount(data.get('box 1a total ordinary dividends', '0'))
        qualified = self._parse_csv_amount(data.get('box 1b qualified dividends', '0'))
        cap_gains = self._parse_csv_amount(data.get('box 2a total capital gain', '0'))
        fed_withheld = self._parse_csv_amount(data.get('box 4 federal income tax withheld', '0'))

        form_data = Form1099Div(
            payer_name=payer,
            ordinary_dividends=ordinary,
            qualified_dividends=qualified,
            capital_gain_distributions=cap_gains,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=ordinary > 0,
            form_type='1099-DIV',
            data=form_data,
            confidence=1.0,
            warnings=[]
        )

    def _extract_1099_nec_from_dict(self, data: dict) -> ExtractionResult:
        """Extract 1099-NEC data from key-value dictionary."""
        payer = data.get('payer name', 'Unknown Payer')
        compensation = self._parse_csv_amount(data.get('box 1 nonemployee compensation', '0'))
        fed_withheld = self._parse_csv_amount(data.get('box 4 federal income tax withheld', '0'))

        form_data = Form1099Nec(
            payer_name=payer,
            nonemployee_compensation=compensation,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=compensation > 0,
            form_type='1099-NEC',
            data=form_data,
            confidence=1.0,
            warnings=[]
        )

    def identify_form_type(self, text: str) -> Optional[str]:
        """
        Identify the type of tax form from document text.

        Args:
            text: Document text content

        Returns:
            Form type identifier or None
        """
        text_upper = text.upper()

        # Check for specific form identifiers
        # W-2 patterns (including variations like "W-2", "W2", "WAGE AND TAX")
        if 'W-2' in text_upper or 'W2' in text_upper or 'WAGE AND TAX' in text_upper:
            return 'W-2'
        # 1099-INT patterns
        elif '1099-INT' in text_upper or ('1099' in text_upper and 'INTEREST INCOME' in text_upper):
            return '1099-INT'
        # 1099-DIV patterns
        elif '1099-DIV' in text_upper or ('1099' in text_upper and 'DIVIDENDS' in text_upper):
            return '1099-DIV'
        # 1099-NEC patterns
        elif '1099-NEC' in text_upper or 'NONEMPLOYEE COMPENSATION' in text_upper:
            return '1099-NEC'
        # 1099-MISC patterns
        elif '1099-MISC' in text_upper or 'MISCELLANEOUS INCOME' in text_upper:
            return '1099-MISC'
        # 1099-B (brokerage) patterns
        elif '1099-B' in text_upper or ('1099' in text_upper and 'PROCEEDS FROM BROKER' in text_upper):
            return '1099-B'
        # 1099-R (retirement) patterns
        elif '1099-R' in text_upper or ('1099' in text_upper and 'DISTRIBUTIONS FROM PENSIONS' in text_upper):
            return '1099-R'
        # 1099-G (government payments) patterns
        elif '1099-G' in text_upper or ('1099' in text_upper and 'GOVERNMENT PAYMENTS' in text_upper):
            return '1099-G'
        # 1098-T (tuition) patterns - check before generic 1098
        elif '1098-T' in text_upper or ('1098' in text_upper and 'TUITION' in text_upper):
            return '1098-T'
        # 1098 (mortgage interest) patterns
        elif '1098' in text_upper and 'MORTGAGE' in text_upper:
            return '1098'

        return None

    def _extract_value(self, text: str, patterns: List[str]) -> Tuple[Optional[str], float]:
        """
        Extract a value using multiple regex patterns.

        Args:
            text: Text to search
            patterns: List of regex patterns to try

        Returns:
            Tuple of (extracted value, confidence score)
        """
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                # Higher confidence for earlier patterns (more specific)
                confidence = 1.0 - (i * 0.1)
                return match.group(1), max(confidence, 0.5)
        return None, 0.0

    def _parse_amount(self, value: Optional[str]) -> float:
        """
        Parse a monetary amount string to float.

        Args:
            value: String representation of amount

        Returns:
            Float value (0.0 if parsing fails)
        """
        if not value:
            return 0.0
        try:
            # Remove commas and dollar signs
            clean = value.replace(',', '').replace('$', '').strip()
            return float(clean)
        except ValueError:
            return 0.0

    def extract_w2(self, document: ParsedDocument) -> ExtractionResult:
        """
        Extract W-2 data from a parsed document.

        Args:
            document: Parsed document content

        Returns:
            ExtractionResult with W2Data if successful
        """
        text = document.text_content
        warnings = []
        confidence_scores = []

        # Extract employer name
        employer_name, conf = self._extract_value(text, self.W2_PATTERNS['employer_name'])
        if not employer_name:
            employer_name = "Unknown Employer"
            warnings.append("Could not extract employer name")
        else:
            confidence_scores.append(conf)

        # Extract other fields
        ein, _ = self._extract_value(text, self.W2_PATTERNS['employer_ein'])

        wages_str, conf = self._extract_value(text, self.W2_PATTERNS['wages'])
        wages = self._parse_amount(wages_str)
        if wages > 0:
            confidence_scores.append(conf)
        else:
            warnings.append("Could not extract wages (Box 1)")

        fed_withheld_str, conf = self._extract_value(text, self.W2_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)
        confidence_scores.append(conf) if fed_withheld > 0 else None

        ss_wages_str, _ = self._extract_value(text, self.W2_PATTERNS['social_security_wages'])
        ss_wages = self._parse_amount(ss_wages_str)

        ss_tax_str, _ = self._extract_value(text, self.W2_PATTERNS['social_security_tax'])
        ss_tax = self._parse_amount(ss_tax_str)

        medicare_wages_str, _ = self._extract_value(text, self.W2_PATTERNS['medicare_wages'])
        medicare_wages = self._parse_amount(medicare_wages_str)

        medicare_tax_str, _ = self._extract_value(text, self.W2_PATTERNS['medicare_tax'])
        medicare_tax = self._parse_amount(medicare_tax_str)

        state, _ = self._extract_value(text, self.W2_PATTERNS['state'])

        state_wages_str, _ = self._extract_value(text, self.W2_PATTERNS['state_wages'])
        state_wages = self._parse_amount(state_wages_str)

        state_withheld_str, _ = self._extract_value(text, self.W2_PATTERNS['state_withheld'])
        state_withheld = self._parse_amount(state_withheld_str)

        # Create W2Data object
        w2_data = W2Data(
            employer_name=employer_name.strip() if employer_name else "Unknown",
            employer_ein=ein,
            wages=wages,
            federal_withheld=fed_withheld,
            social_security_wages=ss_wages,
            social_security_tax=ss_tax,
            medicare_wages=medicare_wages,
            medicare_tax=medicare_tax,
            state=state,
            state_wages=state_wages,
            state_withheld=state_withheld
        )

        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        return ExtractionResult(
            success=wages > 0,
            form_type='W-2',
            data=w2_data,
            confidence=avg_confidence,
            warnings=warnings
        )

    def extract_1099_int(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-INT data from a parsed document."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_INT_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"
            warnings.append("Could not extract payer name")

        interest_str, conf = self._extract_value(text, self.FORM_1099_INT_PATTERNS['interest_income'])
        interest = self._parse_amount(interest_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_INT_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        data = Form1099Int(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            interest_income=interest,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=interest > 0,
            form_type='1099-INT',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract_1099_div(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-DIV data from a parsed document."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_DIV_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"
            warnings.append("Could not extract payer name")

        ordinary_div_str, conf = self._extract_value(text, self.FORM_1099_DIV_PATTERNS['ordinary_dividends'])
        ordinary_div = self._parse_amount(ordinary_div_str)

        qualified_div_str, _ = self._extract_value(text, self.FORM_1099_DIV_PATTERNS['qualified_dividends'])
        qualified_div = self._parse_amount(qualified_div_str)

        cap_gain_str, _ = self._extract_value(text, self.FORM_1099_DIV_PATTERNS['capital_gain_distributions'])
        cap_gain = self._parse_amount(cap_gain_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_DIV_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        data = Form1099Div(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            ordinary_dividends=ordinary_div,
            qualified_dividends=qualified_div,
            capital_gain_distributions=cap_gain,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=ordinary_div > 0,
            form_type='1099-DIV',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract_1099_nec(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-NEC data from a parsed document."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_NEC_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"
            warnings.append("Could not extract payer name")

        compensation_str, conf = self._extract_value(text, self.FORM_1099_NEC_PATTERNS['nonemployee_compensation'])
        compensation = self._parse_amount(compensation_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_NEC_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        data = Form1099Nec(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            nonemployee_compensation=compensation,
            federal_withheld=fed_withheld
        )

        return ExtractionResult(
            success=compensation > 0,
            form_type='1099-NEC',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract_1099_r(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-R data from a parsed document."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_R_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"
            warnings.append("Could not extract payer name")

        gross_str, conf = self._extract_value(text, self.FORM_1099_R_PATTERNS['gross_distribution'])
        gross = self._parse_amount(gross_str)

        taxable_str, _ = self._extract_value(text, self.FORM_1099_R_PATTERNS['taxable_amount'])
        taxable = self._parse_amount(taxable_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_R_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        state_withheld_str, _ = self._extract_value(text, self.FORM_1099_R_PATTERNS['state_withheld'])
        state_withheld = self._parse_amount(state_withheld_str)

        data = Form1099R(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            gross_distribution=gross,
            taxable_amount=taxable if taxable > 0 else gross,
            federal_withheld=fed_withheld,
            state_withheld=state_withheld
        )

        return ExtractionResult(
            success=gross > 0,
            form_type='1099-R',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract_1098(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1098 data from a parsed document."""
        text = document.text_content
        warnings = []

        lender_name, _ = self._extract_value(text, self.FORM_1098_PATTERNS['lender_name'])
        if not lender_name:
            lender_name = "Unknown Lender"
            warnings.append("Could not extract lender name")

        interest_str, conf = self._extract_value(text, self.FORM_1098_PATTERNS['mortgage_interest'])
        interest = self._parse_amount(interest_str)

        taxes_str, _ = self._extract_value(text, self.FORM_1098_PATTERNS['property_taxes'])
        taxes = self._parse_amount(taxes_str)

        data = Form1098(
            lender_name=lender_name.strip() if lender_name else "Unknown",
            mortgage_interest=interest,
            property_taxes=taxes
        )

        return ExtractionResult(
            success=interest > 0,
            form_type='1098',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract(self, document: ParsedDocument, category_hint: Optional[str] = None) -> ExtractionResult:
        """
        Auto-detect form type and extract data.

        Args:
            document: Parsed document content
            category_hint: Optional category from folder-based classification
                           (e.g. 'W-2', '1099-INT'). Used as fallback when
                           text-based identification fails.

        Returns:
            ExtractionResult with appropriate form data
        """
        # Try CSV extraction first for spreadsheet files
        if document.file_type == 'spreadsheet' and document.raw_data is not None:
            csv_result = self._extract_from_csv(document)
            if csv_result and csv_result.success:
                return csv_result

        # Fall back to regex-based extraction for PDF/images
        form_type = self.identify_form_type(document.text_content)

        # Use category hint as fallback when text-based identification fails
        if not form_type and category_hint:
            form_type = category_hint

        if form_type == 'W-2':
            return self.extract_w2(document)
        elif form_type == '1099-INT':
            return self.extract_1099_int(document)
        elif form_type == '1099-DIV':
            return self.extract_1099_div(document)
        elif form_type == '1099-NEC':
            return self.extract_1099_nec(document)
        elif form_type == '1099-R':
            return self.extract_1099_r(document)
        elif form_type == '1098':
            return self.extract_1098(document)
        elif form_type == '1099-G':
            return ExtractionResult(
                success=False,
                form_type='1099-G',
                data=None,
                confidence=0.0,
                warnings=[f"1099-G detected but extraction not yet implemented: {document.file_path}"]
            )
        elif form_type == '1098-T':
            return ExtractionResult(
                success=False,
                form_type='1098-T',
                data=None,
                confidence=0.0,
                warnings=[f"1098-T detected but extraction not yet implemented: {document.file_path}"]
            )
        elif form_type == '1099-B':
            # 1099-B is complex, return basic info
            return ExtractionResult(
                success=False,
                form_type='1099-B',
                data=None,
                confidence=0.0,
                warnings=[f"1099-B detected but requires manual review: {document.file_path}"]
            )
        else:
            return ExtractionResult(
                success=False,
                form_type=None,
                data=None,
                confidence=0.0,
                warnings=[f"Could not identify form type in {document.file_path}"]
            )

    def extract_all(
        self,
        documents: List[ParsedDocument],
        category_hints: Optional[dict] = None,
    ) -> List[ExtractionResult]:
        """
        Extract tax data from multiple documents.

        Args:
            documents: List of parsed documents
            category_hints: Optional dict mapping file paths to category strings
                            from folder-based classification.

        Returns:
            List of extraction results
        """
        results = []
        for doc in documents:
            hint = (category_hints or {}).get(doc.file_path)
            result = self.extract(doc, category_hint=hint)
            results.append(result)
            if result.success:
                print(f"Extracted {result.form_type} from {doc.file_path}")
            else:
                print(f"Could not extract data from {doc.file_path}: {result.warnings}")
        return results
