"""Extract structured tax data from parsed documents."""

import re
from datetime import date as date_type
from typing import Optional, List, Tuple
from dataclasses import dataclass

from .document_parser import ParsedDocument
from .models import (
    W2Data, Form1099Int, Form1099Div, Form1099Misc, Form1099Nec,
    Form1099R, Form1099B, Form1099G, Form1098, Form1098T,
    MiscDeductionDoc, RentalProperty,
    CAVehicleRegistration, EstimatedTaxPayment, DependentCareFSA,
)


@dataclass
class ExtractionResult:
    """Result of data extraction attempt."""
    success: bool
    form_type: Optional[str]
    data: Optional[object]
    confidence: float
    warnings: List[str]
    source_file: str = ""
    source_text: str = ""


@dataclass
class DocumentOnly:
    """Placeholder for documents we recognized but do not extract structured data from."""
    category: str = ""
    description: str = ""


@dataclass
class PropertyTaxParcel:
    """A single parcel/property from a property tax receipt."""
    apn: str = ""
    address: str = ""
    amount: float = 0.0


@dataclass
class PropertyTaxReceipt:
    """Extracted property tax payment (Schedule A for primary; Schedule E for rental)."""
    amount: float = 0.0
    payment_date: Optional[date_type] = None  # Filter by tax year (e.g. 2025 only)
    is_rental: bool = False  # True => apply to rental property's property_tax (Schedule E)
    parcels: list = None  # List[PropertyTaxParcel] when multiple parcels detected
    address: str = ""  # Property address (from payment history format)


@dataclass
class CharitableContributionDoc:
    """Extracted charitable contribution amount (for Schedule A)."""
    amount: float = 0.0


class TaxDataExtractor:
    """Extract tax form data from parsed documents."""

    # Keywords that indicate a composite/consolidated 1099 statement
    COMPOSITE_INDICATORS = [
        'TAX REPORTING STATEMENT',
        '1099 COMPOSITE',
        'FORM 1099 COMPOSITE',
        'CONSOLIDATED TAX',
        'CONSOLIDATED 1099',
    ]

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
            # Labeled field pattern (most reliable)
            r"Federal\s+income\s+tax\s+withheld\s*\$?([\d,]+\.?\d*)",
            # Second number in the pair
            r"[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})\s*\n.*?3\s*Social",
            r"2\s+Federal.*?\n\s*[\d,]+\.?\d{2}\s+([\d,]+\.?\d{2})",
            r"2\s+Federal\s+income\s+tax\s+withheld[\s\S]{0,60}\$([\d,]+\.\d{2})",
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
            r"[Pp]ayer.?s\s+name:\s*([A-Z][A-Za-z\s&.,]+)",
        ],
        'interest_income': [
            r"([\d,]+\.\d{2})\s*\n\s*1\.\s*INTEREST\s+INCOME",
            r"(?:box\s*1|interest\s+income)[:\s]*\$?([\d,]+\.?\d*)",
            r"1\s+Interest\s+income[^$]*\$?([\d,]+\.?\d*)",
        ],
        'us_treasury_interest': [
            r"(?:box\s*3|interest\s+on\s+U\.?S\.?\s*(?:savings|treasury))[:\s]*\$?([\d,]+\.?\d*)",
            r"3[\s.,-]+Interest\s*on\s*U\.?S\.?.*?(?:Treas|Treasury).*?([\d,]+\.\d{2})",
            r"U\.?S\.?\s*(?:Savings|Treasury)\s+(?:Bonds?\s+)?(?:and\s+)?(?:Treasury\s+)?[Oo]bligations.*?\$?([\d,]+\.?\d*)",
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

    # 1099-MISC patterns
    FORM_1099_MISC_PATTERNS = {
        'payer_name': [
            r"(?:payer'?s?\s+name)[:\s]*([A-Z][A-Za-z\s&.,]+)",
        ],
        'rents': [
            r"(?:box\s*1|rents)[:\s]*\$?([\d,]+\.?\d*)",
            r"1\s+Rents[^$]*\$?([\d,]+\.?\d*)",
        ],
        'other_income': [
            r"(?:box\s*3|other\s+income)[:\s]*\$?([\d,]+\.?\d*)",
            r"3\s+Other\s+income[^$]*\$?([\d,]+\.?\d*)",
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
        'distribution_code': [
            r"7\s*Distribution\s*code\(?s?\)?[\s\S]{0,30}?([1-9A-Z]{1,2})\b",
            r"(?:box\s*7|distribution\s+code)[:\s]*([1-9A-Z]{1,2})\b",
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
        'property_address': [
            r"8\s*(?:Address|ADDR)\w*\s*(?:or\s*description\s*)?(?:of\s*)?(?:property|prop).*?\n\s*(.+)",
            r"[Pp]roperty\s+[Aa]ddress[:\s]*\n?\s*(.+)",
            r"(?:securing\s+(?:the\s+)?mortgage)[:\s]*\n?\s*(.+)",
        ],
    }

    # 1099-G patterns (government payments: unemployment, state refund)
    FORM_1099_G_PATTERNS = {
        'payer_name': [
            r"(?:payer'?s?\s+name|PAYER)[:\s]*([A-Z][A-Za-z\s&.,]+(?:DEPARTMENT|STATE|COUNTY|TREASURY)?)",
            r"([A-Z][A-Za-z\s]+(?:State|County|Employment)\s+(?:Department|Development))",
        ],
        'unemployment_compensation': [
            r"1\s*Unemployment\s+compensation[\s\S]{0,60}\$?([\d,]+\.?\d*)",
            r"(?:box\s*1|unemployment\s+compensation)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'state_tax_refund': [
            r"2\s*State\s+or\s+local\s+income\s+tax\s+refunds[\s\S]{0,60}\$?([\d,]+\.?\d*)",
            r"(?:box\s*2|state\s+.*?tax\s+refund)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'federal_withheld': [
            r"4\s*Federal\s+income\s+tax\s+withheld[\s\S]{0,60}\$?([\d,]+\.?\d*)",
            r"(?:box\s*4|federal\s+income\s+tax\s+withheld)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # 1098-T patterns (tuition)
    FORM_1098_T_PATTERNS = {
        'institution_name': [
            r"(?:recipient'?s?|institution'?s?)\s+name[^A-Z]*([A-Z][A-Za-z\s&.,]+(?:University|College|Institute|School)?)",
            r"([A-Z][A-Za-z\s&.,]+(?:University|College|Institute))",
        ],
        'amounts_billed': [
            r"1\s*(?:Payments\s+received|Amounts\s+billed)[\s\S]{0,80}\$?([\d,]+\.?\d*)",
            r"(?:box\s*1|amounts\s+billed|payments\s+received)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        'scholarships_grants': [
            r"5\s*Scholarships[\s\S]{0,80}\$?([\d,]+\.?\d*)",
            r"(?:box\s*5|scholarships\s+and\s+grants)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    # Estimated tax payment receipt patterns (1040-ES, 540-ES, Pay1040, etc.)
    ESTIMATED_PAYMENT_PATTERNS = {
        'amount': [
            r"(?:amount\s+paid|payment\s+amount|total\s+paid)[:\s]*\$?([\d,]+\.?\d{2})",
            r"\$\s*([\d,]+\.\d{2})\s*(?:paid|payment)",
            r"(?:paid|amount)[:\s]*\$?\s*([\d,]+\.?\d{2})",
            r"([\d,]+\.\d{2})\s*(?:USD|dollars)",
        ],
        'date': [
            r"(?:date\s+paid|payment\s+date|date)[:\s]*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
            r"(\d{4})[-/](\d{2})[-/](\d{2})",
        ],
        'federal_indicator': [
            r"1040[- ]?ES|Form\s+1040|Pay1040|federal\s+estimated",
        ],
        'ca_indicator': [
            r"540[- ]?ES|Form\s+540|California\s+estimated|state\s+estimated",
        ],
    }

    # Vehicle registration (CA: VLF is deductible)
    # CA DMV uses "Vehicle License Fee", "VLF", "Registration Fee", "Total Due", etc.
    VEHICLE_REGISTRATION_PATTERNS = {
        'vehicle_license_fee': [
            r"(?:vehicle\s+license\s+fee|VLF|license\s+fee)[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"\$?\s*([\d,]+\.\d{2})\s*(?:vehicle\s+license|VLF|license\s+fee)",
            r"(?:vehicle\s+license|VLF)[\s\S]{0,40}?\$?\s*([\d,]+\.\d{2})",
            r"([\d,]+\.\d{2})\s*[\s\S]{0,30}?(?:vehicle\s+license|VLF)",
        ],
        'total_registration_fee': [
            r"(?:total\s+due|amount\s+due|balance\s+due|pay\s+this\s+amount)[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"(?:registration\s+total|total\s+registration|total\s+fees?|fees?\s+due)[:\s]*\$?\s*([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.\d{2})\s*(?:total|due|payable)",
            r"(?:total|amount)\s*[:\s]*\$?\s*([\d,]+\.\d{2})",
            r"([\d,]+\.\d{2})\s*(?:USD|dollars?|total)",
        ],
    }
    # Fallback: any dollar amount on doc (used when labeled patterns miss)
    VEHICLE_REGISTRATION_ANY_AMOUNT = re.compile(r"\$\s*([\d,]+\.\d{2})|([\d,]+\.\d{2})\s*\$?")

    # Property tax receipt (amount + date for tax-year filter)
    PROPERTY_TAX_PATTERNS = [
        r"(?:amount\s+paid|total\s+paid|payment\s+amount|total\s+due|amount\s+due)[:\s]*\$?([\d,]+\.?\d{2})",
        r"\$\s*([\d,]+\.\d{2})",
        r"([\d,]+\.\d{2})\s*(?:paid|due|USD)",
    ]
    PROPERTY_TAX_DATE_PATTERNS = [
        r"(?:payment\s+date|date\s+paid|transaction\s+date|date)[:\s]*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
        r"(?:paid|date)[:\s]*(\d{4})[-/](\d{2})[-/](\d{2})",
        r"(\d{4})[-/](\d{2})[-/](\d{2})",
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
    ]
    # Filename: e.g. Receipt-online-11062025-575.pdf or receipt_20251106.pdf
    PROPERTY_TAX_FILENAME_DATE = re.compile(
        r"(?:^|[\-_])(\d{4})(\d{2})(\d{2})(?:\D|$)|"  # YYYYMMDD
        r"(?:^|[\-_])(\d{2})(\d{2})(\d{4})(?:\D|$)"   # MMDDYYYY
    )

    # FSA / dependent care receipt
    FSA_PATTERNS = {
        'amount_paid': [
            r"(?:amount\s+paid|total\s+paid|payment)[:\s]*\$?([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.?\d*)",
        ],
        'fsa_contribution': [
            r"(?:FSA|contribution|reimbursement)[:\s]*\$?([\d,]+\.?\d*)",
        ],
    }

    def __init__(self, tax_year: int = 0):
        """Initialize the tax data extractor."""
        self.tax_year = tax_year

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
        # Composite brokerage statements (1099-B) must be detected BEFORE W-2,
        # because these PDFs contain "W-2" in their instructional boilerplate.
        # A real W-2 would never contain "PROCEEDS FROM BROKER" or "1099-B".
        if '1099-B' in text_upper or 'PROCEEDS FROM BROKER' in text_upper:
            return '1099-B'
        # W-2 patterns (including variations like "W-2", "W2", "WAGE AND TAX")
        if 'W-2' in text_upper or 'W2' in text_upper or 'WAGE AND TAX' in text_upper:
            return 'W-2'
        # 1099-INT patterns
        if '1099-INT' in text_upper or ('1099' in text_upper and 'INTEREST INCOME' in text_upper):
            return '1099-INT'
        # 1099-DIV patterns
        if '1099-DIV' in text_upper or ('1099' in text_upper and 'DIVIDENDS' in text_upper):
            return '1099-DIV'
        # 1099-NEC patterns
        if '1099-NEC' in text_upper or 'NONEMPLOYEE COMPENSATION' in text_upper:
            return '1099-NEC'
        # 1099-MISC patterns
        if '1099-MISC' in text_upper or 'MISCELLANEOUS INCOME' in text_upper:
            return '1099-MISC'
        # 1099-R (retirement) patterns
        if '1099-R' in text_upper or ('1099' in text_upper and 'DISTRIBUTIONS FROM PENSIONS' in text_upper):
            return '1099-R'
        # 1099-G (government payments) patterns
        if '1099-G' in text_upper or ('1099' in text_upper and 'GOVERNMENT PAYMENTS' in text_upper):
            return '1099-G'
        # 1098-T (tuition) patterns - check before generic 1098
        if '1098-T' in text_upper or ('1098' in text_upper and 'TUITION' in text_upper):
            return '1098-T'
        # 1098 (mortgage interest) patterns
        if '1098' in text_upper and 'MORTGAGE' in text_upper:
            return '1098'

        # --- Non-IRS document types (content-based) ---
        # Property Tax
        if any(kw in text_upper for kw in [
            'PARCEL NUMBER', 'SECURED TAX', 'PROPERTY TAX',
            'REAL ESTATE TAX', 'TAX COLLECTOR', 'ASSESSED VALUE',
            'ANNUAL TAX BILL', 'TAX AND COLLECTIONS',
        ]):
            return 'Property Tax'
        # Vehicle Registration
        if any(kw in text_upper for kw in [
            'VEHICLE LICENSE FEE', 'VLF', 'REGISTRATION RENEWAL', 'DMV',
        ]):
            return 'Vehicle Registration'
        # Estimated Payment
        if any(kw in text_upper for kw in [
            '1040-ES', '540-ES', 'ESTIMATED TAX PAYMENT', 'PAYMENT VOUCHER',
            'ESTIMATED 1040ES', 'INDIVIDUAL ESTIMATED TAX',
        ]):
            return 'Estimated Payment'
        # FSA
        if any(kw in text_upper for kw in [
            'FLEXIBLE SPENDING', 'DEPENDENT CARE', 'DCFSA', 'FSA',
        ]):
            return 'FSA'
        # Charitable Contribution
        if any(kw in text_upper for kw in [
            'TAX-DEDUCTIBLE', 'CHARITABLE CONTRIBUTION', 'DONATION RECEIPT',
        ]):
            return 'Charitable Contribution'
        # Misc Deduction
        if any(kw in text_upper for kw in [
            'ADVISORY FEE', 'INVESTMENT MANAGEMENT FEE', 'TAX PREPARATION FEE',
        ]):
            return 'Misc Deduction'
        # Schedule E (property management statements)
        if any(kw in text_upper for kw in [
            'PROPERTY MANAGEMENT', 'OWNER STATEMENT',
        ]):
            return 'Schedule E'

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

        treasury_str, _ = self._extract_value(text, self.FORM_1099_INT_PATTERNS['us_treasury_interest'])
        treasury = self._parse_amount(treasury_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_INT_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        data = Form1099Int(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            interest_income=interest,
            us_treasury_interest=treasury,
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

    def extract_1099_misc(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-MISC data from a parsed document."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_MISC_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"
            warnings.append("Could not extract payer name")

        rents_str, _ = self._extract_value(text, self.FORM_1099_MISC_PATTERNS['rents'])
        rents = self._parse_amount(rents_str)

        other_str, conf = self._extract_value(text, self.FORM_1099_MISC_PATTERNS['other_income'])
        other = self._parse_amount(other_str)

        fed_withheld_str, _ = self._extract_value(text, self.FORM_1099_MISC_PATTERNS['federal_withheld'])
        fed_withheld = self._parse_amount(fed_withheld_str)

        data = Form1099Misc(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            rents=rents,
            other_income=other,
            federal_withheld=fed_withheld,
        )

        return ExtractionResult(
            success=rents > 0 or other > 0,
            form_type='1099-MISC',
            data=data,
            confidence=conf,
            warnings=warnings,
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

        dist_code, _ = self._extract_value(text, self.FORM_1099_R_PATTERNS['distribution_code'])

        # If taxable amount couldn't be parsed, flag it as not determined
        taxable_not_determined = (taxable <= 0 and gross > 0)

        data = Form1099R(
            payer_name=payer_name.strip() if payer_name else "Unknown",
            gross_distribution=gross,
            taxable_amount=taxable if taxable > 0 else gross,
            taxable_amount_not_determined=taxable_not_determined,
            federal_withheld=fed_withheld,
            distribution_code=dist_code if dist_code else "",
            state_withheld=state_withheld,
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

        prop_addr, _ = self._extract_value(text, self.FORM_1098_PATTERNS['property_address'])

        data = Form1098(
            lender_name=lender_name.strip() if lender_name else "Unknown",
            mortgage_interest=interest,
            property_taxes=taxes,
            property_address=prop_addr.strip() if prop_addr else "",
        )

        return ExtractionResult(
            success=interest > 0,
            form_type='1098',
            data=data,
            confidence=conf,
            warnings=warnings
        )

    def extract_1099_g(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1099-G data (government payments: unemployment, state refund)."""
        text = document.text_content
        warnings = []

        payer_name, _ = self._extract_value(text, self.FORM_1099_G_PATTERNS['payer_name'])
        if not payer_name:
            payer_name = "Unknown Payer"

        unemp_str, c1 = self._extract_value(text, self.FORM_1099_G_PATTERNS['unemployment_compensation'])
        refund_str, c2 = self._extract_value(text, self.FORM_1099_G_PATTERNS['state_tax_refund'])
        fed_str, c3 = self._extract_value(text, self.FORM_1099_G_PATTERNS['federal_withheld'])

        unemp = self._parse_amount(unemp_str)
        refund = self._parse_amount(refund_str)
        fed = self._parse_amount(fed_str)

        data = Form1099G(
            payer_name=payer_name.strip(),
            unemployment_compensation=unemp,
            state_tax_refund=refund,
            federal_withheld=fed,
        )
        success = unemp > 0 or refund > 0
        conf = max(c1, c2, c3) if success else 0.0
        if not success:
            warnings.append("No Box 1 or Box 2 amount found")
        return ExtractionResult(
            success=success,
            form_type='1099-G',
            data=data,
            confidence=conf,
            warnings=warnings,
        )

    def extract_1098_t(self, document: ParsedDocument) -> ExtractionResult:
        """Extract 1098-T data (tuition: amounts billed, scholarships)."""
        text = document.text_content
        warnings = []

        inst_name, _ = self._extract_value(text, self.FORM_1098_T_PATTERNS['institution_name'])
        if not inst_name:
            inst_name = "Unknown Institution"
            warnings.append("Could not extract institution name")

        billed_str, c1 = self._extract_value(text, self.FORM_1098_T_PATTERNS['amounts_billed'])
        schol_str, c2 = self._extract_value(text, self.FORM_1098_T_PATTERNS['scholarships_grants'])
        amounts_billed = self._parse_amount(billed_str)
        scholarships_grants = self._parse_amount(schol_str)

        data = Form1098T(
            institution_name=inst_name.strip(),
            amounts_billed=amounts_billed,
            scholarships_grants=scholarships_grants,
        )
        success = amounts_billed > 0 or scholarships_grants > 0
        conf = max(c1, c2) if success else 0.0
        if not success:
            warnings.append("No Box 1 or Box 5 amount found")
        return ExtractionResult(
            success=success,
            form_type='1098-T',
            data=data,
            confidence=conf,
            warnings=warnings,
        )

    def extract_estimated_payment(self, document: ParsedDocument) -> ExtractionResult:
        """Extract estimated tax payment amount and jurisdiction from receipt/confirmation."""
        text = document.text_content
        text_upper = text.upper()
        warnings = []

        amount = 0.0
        for pattern in self.ESTIMATED_PAYMENT_PATTERNS['amount']:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                amount = self._parse_amount(m.group(1))
                if amount > 0:
                    break

        jurisdiction = "federal"
        if any(re.search(p, text_upper) for p in self.ESTIMATED_PAYMENT_PATTERNS['ca_indicator']):
            jurisdiction = "california"
        elif any(re.search(p, text_upper) for p in self.ESTIMATED_PAYMENT_PATTERNS['federal_indicator']):
            jurisdiction = "federal"

        payment_date = None
        for pattern in self.ESTIMATED_PAYMENT_PATTERNS['date']:
            m = re.search(pattern, text)
            if m:
                g = m.groups()
                if len(g) == 3:
                    try:
                        a, b, c = int(g[0]), int(g[1]), int(g[2])
                        if a > 31:  # YYYY-MM-DD
                            payment_date = date_type(a, b, c)
                        elif c > 31:  # MM-DD-YYYY or DD-MM-YYYY
                            payment_date = date_type(c, a, b) if a <= 12 else date_type(c, b, a)
                        else:
                            if a <= 12 and b <= 31:
                                y = c + 2000 if c < 100 else c
                                payment_date = date_type(y, a, b)
                        if payment_date:
                            break
                    except (ValueError, TypeError):
                        pass

        if amount <= 0:
            warnings.append("Could not extract payment amount")
        data = EstimatedTaxPayment(
            payment_date=payment_date,
            amount=amount,
            period="",
            jurisdiction=jurisdiction,
        )
        return ExtractionResult(
            success=amount > 0,
            form_type='Estimated Payment',
            data=data,
            confidence=0.7 if amount > 0 else 0.0,
            warnings=warnings,
        )

    def extract_vehicle_registration(self, document: ParsedDocument) -> ExtractionResult:
        """Extract CA vehicle registration / VLF for Schedule A."""
        text = document.text_content
        warnings = []

        vlf_str, _ = self._extract_value(text, self.VEHICLE_REGISTRATION_PATTERNS['vehicle_license_fee'])
        total_str, _ = self._extract_value(text, self.VEHICLE_REGISTRATION_PATTERNS['total_registration_fee'])
        vlf = self._parse_amount(vlf_str)
        total = self._parse_amount(total_str)
        if vlf == 0 and total > 0:
            vlf = total  # Use total as fallback; user can correct
        if total == 0 and vlf > 0:
            total = vlf

        # Fallback: grab any dollar amounts from text (DMV docs vary; OCR may not match labels)
        if vlf == 0 and total == 0:
            amounts = []
            for m in self.VEHICLE_REGISTRATION_ANY_AMOUNT.finditer(text):
                val = self._parse_amount(m.group(1) or m.group(2))
                if 20 <= val <= 2000:  # Plausible CA registration/VLF range
                    amounts.append(val)
            if amounts:
                # Use largest amount as total; treat as VLF (user can correct)
                total = max(amounts)
                vlf = total
                warnings.append("Used fallback amount (no VLF/total label found); verify for Schedule A")

        data = CAVehicleRegistration(
            total_registration_fee=total,
            vehicle_license_fee=vlf,
        )
        success = vlf > 0 or total > 0
        if not success:
            warnings.append("Could not extract VLF or total registration amount")
        return ExtractionResult(
            success=success,
            form_type='Vehicle Registration',
            data=data,
            confidence=0.5 if (success and warnings) else (0.7 if success else 0.0),
            warnings=warnings,
        )

    def _parse_property_tax_date(self, text: str, file_path: str) -> Optional[date_type]:
        """Extract payment date from receipt text or filename (MMDDYYYY/YYYYMMDD)."""
        # Try document text first
        for pattern in self.PROPERTY_TAX_DATE_PATTERNS:
            m = re.search(pattern, text)
            if m:
                g = m.groups()
                try:
                    if len(g[0]) == 4 and int(g[0]) > 31:  # YYYY-MM-DD
                        return date_type(int(g[0]), int(g[1]), int(g[2]))
                    # M/D/YY or M/D/YYYY (g0=mo, g1=day, g2=year)
                    y = int(g[2])
                    if y < 100:
                        y += 2000
                    mo, d = int(g[0]), int(g[1])
                    if 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2100:
                        return date_type(y, mo, d)
                except (ValueError, TypeError, IndexError):
                    pass
        # Try filename: MMDDYYYY (e.g. 11062025) or YYYYMMDD
        import os
        name = os.path.basename(file_path)
        for m in self.PROPERTY_TAX_FILENAME_DATE.finditer(name):
            try:
                g1, g2, g3 = m.group(1), m.group(2), m.group(3)
                if len(g1) == 4 and int(g1) > 1900:  # YYYYMMDD
                    return date_type(int(g1), int(g2), int(g3))
                # MMDDYYYY
                mo, d, y = int(g1), int(g2), int(g3)
                if 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2100:
                    return date_type(y, mo, d)
            except (ValueError, TypeError, IndexError):
                pass
        return None

    def _extract_payment_history_property_tax(self, text: str, tax_year: int) -> Optional[PropertyTaxReceipt]:
        """Extract from Santa Clara County payment history format.

        Sums payments whose 'Payment Posted' date falls in the given calendar year.
        Returns None if the format doesn't match.
        """
        addr_m = re.search(r'Property Address\s+(.+?)(?:\n|Tax Rate)', text)
        parcel_m = re.search(r'Parcel Number\s+(\d+)', text)
        if not addr_m and not parcel_m:
            return None

        address = addr_m.group(1).strip() if addr_m else ""
        apn = parcel_m.group(1) if parcel_m else ""

        # Parse payment rows: FY, suffix, installment, tax_amount, add_charges, paid, date
        rows = re.findall(
            r'(\d{4})\s+\d+\s+(\d)\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s+\$([\d,]+\.\d{2})\s+(\d{2}/\d{2}/\d{4})',
            text,
        )
        total = 0.0
        for _fy, _inst, _tax_amt, paid_str, date_str in rows:
            paid = self._parse_amount(paid_str)
            # Filter by payment date in the target calendar year
            try:
                payment_year = int(date_str.split('/')[-1])
            except (ValueError, IndexError):
                continue
            if payment_year == tax_year and paid > 0:
                total += paid

        if total <= 0:
            return None

        return PropertyTaxReceipt(
            amount=round(total, 2),
            address=address,
            parcels=[PropertyTaxParcel(apn=apn, address=address, amount=round(total, 2))],
        )

    def extract_property_tax(self, document: ParsedDocument, tax_year: int = 0) -> ExtractionResult:
        """Extract property tax payment (amount, date, primary vs rental from path)."""
        text = document.text_content
        path_lower = document.file_path.lower()
        warnings = []

        # Format 1: Santa Clara County payment history (has Property Address + tabular rows)
        history = self._extract_payment_history_property_tax(text, tax_year)
        if history:
            is_rental = (
                "rental" in path_lower or "rent_home" in path_lower
                or "rent_" in path_lower or "rent " in path_lower
            )
            history.is_rental = is_rental
            return ExtractionResult(
                success=True,
                form_type='Property Tax',
                data=history,
                confidence=0.8,
                warnings=[],
            )

        # Format 2: Simple receipt with APN-based parcels
        parcels = []
        parcel_matches = re.findall(
            r'APN:\s*([\d\-]+).*?(?:Installment\s+\d+|Amount)\s+([\d,]+\.\d{2})',
            text, re.DOTALL | re.IGNORECASE,
        )
        for apn, amt_str in parcel_matches:
            amt = self._parse_amount(amt_str)
            if amt > 0:
                parcels.append(PropertyTaxParcel(apn=apn, amount=amt))

        if parcels:
            amount = sum(p.amount for p in parcels)
        else:
            # Format 3: Generic amount patterns
            amount = 0.0
            for pattern in self.PROPERTY_TAX_PATTERNS:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    amount = self._parse_amount(m.group(1))
                    if amount > 0:
                        break

        if amount <= 0:
            warnings.append("Could not extract property tax amount")
        payment_date = self._parse_property_tax_date(text, document.file_path)
        is_rental = (
            "rental" in path_lower or "rent_home" in path_lower
            or "rent_" in path_lower or "rent " in path_lower
        )
        data = PropertyTaxReceipt(
            amount=amount,
            payment_date=payment_date,
            is_rental=is_rental,
            parcels=parcels if len(parcels) > 1 else None,
        )
        return ExtractionResult(
            success=amount > 0,
            form_type='Property Tax',
            data=data,
            confidence=0.6 if amount > 0 else 0.0,
            warnings=warnings,
        )

    def extract_fsa(self, document: ParsedDocument) -> ExtractionResult:
        """Extract FSA / dependent care receipt amounts."""
        text = document.text_content
        warnings = []
        amount_paid_str, _ = self._extract_value(text, self.FSA_PATTERNS['amount_paid'])
        fsa_str, _ = self._extract_value(text, self.FSA_PATTERNS['fsa_contribution'])
        amount_paid = self._parse_amount(amount_paid_str) if amount_paid_str else 0.0
        fsa_contribution = self._parse_amount(fsa_str) if fsa_str else 0.0
        if amount_paid <= 0 and fsa_contribution <= 0:
            for pattern in self.FSA_PATTERNS['amount_paid']:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    amount_paid = self._parse_amount(m.group(1))
                    if amount_paid > 0:
                        break
        data = DependentCareFSA(
            amount_paid=amount_paid,
            fsa_contribution=fsa_contribution,
        )
        success = amount_paid > 0 or fsa_contribution > 0
        if not success:
            warnings.append("Could not extract FSA/dependent care amount")
        return ExtractionResult(
            success=success,
            form_type='FSA',
            data=data,
            confidence=0.6 if success else 0.0,
            warnings=warnings,
        )

    CHARITABLE_PATTERNS = [
        r"(?:donation|contribution|amount\s+donated)[:\s]*\$?([\d,]+\.?\d{2})",
        r"\$\s*([\d,]+\.\d{2})\s*(?:donation|contribution)",
        r"(?:total|amount)\s+(?:paid|given)[:\s]*\$?([\d,]+\.?\d*)",
    ]

    def extract_charitable_contribution(self, document: ParsedDocument) -> ExtractionResult:
        """Extract charitable contribution amount from receipt."""
        text = document.text_content
        warnings = []
        amount = 0.0
        for pattern in self.CHARITABLE_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                amount = self._parse_amount(m.group(1))
                if amount > 0:
                    break
        if amount <= 0:
            warnings.append("Could not extract charitable contribution amount")
        data = CharitableContributionDoc(amount=amount)
        return ExtractionResult(
            success=amount > 0,
            form_type='Charitable Contribution',
            data=data,
            confidence=0.6 if amount > 0 else 0.0,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Misc Deduction (advisory fees, tax prep, etc.)
    # ------------------------------------------------------------------

    MISC_DEDUCTION_PATTERNS = [
        r'(?:advisory|management|investment)\s+fee[s]?.*?\$\s*([\d,]+\.?\d*)',
        r'(?:tax\s+prep(?:aration)?|professional)\s+fee[s]?.*?\$\s*([\d,]+\.?\d*)',
        r'(?:total|amount)\s+(?:fees?|charges?|due).*?\$\s*([\d,]+\.?\d*)',
        r'\$\s*([\d,]+\.\d{2})\s*(?:advisory|management|fee|total)',
    ]

    MISC_DEDUCTION_TYPE_KEYWORDS = {
        'advisory_fee': ['advisory', 'management fee', 'investment fee', 'wealth management'],
        'tax_prep': ['tax prep', 'tax preparation', 'cpa', 'accountant'],
        'employee_expense': ['employee', 'unreimbursed', 'business expense'],
    }

    def extract_misc_deduction(self, document: ParsedDocument) -> ExtractionResult:
        """Extract miscellaneous deduction amounts from fee statements."""
        text = document.text_content
        warnings = []

        # Try each pattern to find an amount
        amount = 0.0
        for pattern in self.MISC_DEDUCTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount > 0:
                    break

        # Determine deduction type from text keywords
        text_lower = text.lower()
        deduction_type = 'other'
        for dtype, keywords in self.MISC_DEDUCTION_TYPE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                deduction_type = dtype
                break

        # Use filename as description fallback
        description = document.file_path.split('/')[-1].split('\\')[-1]

        if amount <= 0:
            warnings.append(f"Could not extract deduction amount from {document.file_path}")

        data = MiscDeductionDoc(
            description=description,
            amount=amount,
            deduction_type=deduction_type,
        )

        return ExtractionResult(
            success=amount > 0,
            form_type='Misc Deduction',
            data=data,
            confidence=0.6 if amount > 0 else 0.0,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Schedule E — Rental Property Management Statements
    # ------------------------------------------------------------------

    def extract_rental_pm_statement(self, document: ParsedDocument) -> ExtractionResult:
        """
        Extract rental property data from a PM statement.

        Supports two document formats:
        1. Excel/CSV expense ledger: columns Date, Property, Vendor,
           Description, Debit, Credit, Note.  Debit column = repair costs.
        2. PDF PM receipt: extracts management fee amount via regex.

        Returns an ExtractionResult with form_type='Schedule E' and
        data=RentalProperty (partially populated with repairs and/or
        management_fees).
        """
        import pandas as pd

        warnings = []
        repairs = 0.0
        management_fees = 0.0
        property_name = ""

        # ----- Excel / CSV path: parse expense ledger -----
        if document.raw_data is not None:
            df = document.raw_data

            # Find the header row containing 'Debit' column
            header_row = None
            for idx in range(min(10, len(df))):
                row_vals = [str(v).strip().lower() for v in df.iloc[idx]]
                if 'debit' in row_vals:
                    header_row = idx
                    break

            if header_row is not None:
                # Re-read with correct header
                df.columns = [str(c).strip() for c in df.iloc[header_row]]
                df = df.iloc[header_row + 1:].reset_index(drop=True)

                # Find Debit column (case-insensitive)
                debit_col = None
                for col in df.columns:
                    if col.lower().strip() == 'debit':
                        debit_col = col
                        break

                if debit_col:
                    # Sum numeric Debit values, excluding total/summary rows
                    for idx, row in df.iterrows():
                        val = row[debit_col]
                        # Check all columns for summary keywords
                        row_text = ' '.join(str(v) for v in row.values if str(v).lower() not in ('nan', 'none', '')).lower()
                        # Skip total/summary rows
                        if 'total' in row_text or 'amount due' in row_text:
                            continue
                        try:
                            amount = float(str(val).replace(',', '').replace('$', ''))
                            if amount > 0:
                                repairs += amount
                        except (ValueError, TypeError):
                            continue

                # Extract property name from Property column
                prop_col = None
                for col in df.columns:
                    if col.lower().strip() == 'property':
                        prop_col = col
                        break
                if prop_col:
                    for val in df[prop_col]:
                        s = str(val).strip()
                        if s and s.lower() not in ('nan', 'none', ''):
                            property_name = s
                            break

                if repairs > 0:
                    repairs = round(repairs, 2)
                else:
                    warnings.append(f"No repair expenses found in Debit column: {document.file_path}")
            else:
                warnings.append(f"Could not find header row with 'Debit' column: {document.file_path}")

        # ----- PDF path: extract management fee via regex -----
        elif document.text_content:
            text = document.text_content
            # Match management / consulting fee patterns
            fee_patterns = [
                r'(?:management|consulting|pm)\s+(?:fee|consulting)\s*[:.]?\s*[$]?([\d,]+\.\d{2})',
                r'[$]\s*([\d,]+\.\d{2})\s*(?:management|consulting|pm)\s+(?:fee|consulting)',
                r'SUBTOTAL\s+[$]([\d,]+\.\d{2})',
                r'PM\s+consulting\s+\d+\s+[$]([\d,]+\.\d{2})',
            ]
            for pattern in fee_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    management_fees = self._parse_amount(match.group(1))
                    if management_fees > 0:
                        break

            # Try to extract property address (California address pattern)
            # Find all CA addresses and prefer the one that's NOT the billing/SOLD TO address
            addr_matches = re.findall(
                r'^(\d{2,}\s+[\w\s]+(?:Ct|St|Ave|Dr|Blvd|Ln|Way|Rd|Pl)[.,]?\s*[\w\s]*,?\s*CA\s*\d{5})',
                text, re.IGNORECASE | re.MULTILINE
            )
            # Use last match (rental property, not billing address) if multiple
            addr_match = addr_matches[-1].strip() if addr_matches else None
            if addr_match:
                property_name = addr_match

            if management_fees <= 0:
                warnings.append(f"Could not extract management fee from PDF: {document.file_path}")

        else:
            return ExtractionResult(
                success=False, form_type='Schedule E', data=None,
                confidence=0.0,
                warnings=[f"Schedule E document has no parseable data: {document.file_path}"],
            )

        has_data = repairs > 0 or management_fees > 0
        rental = RentalProperty(
            address=property_name,
            repairs=repairs,
            management_fees=management_fees,
        )

        return ExtractionResult(
            success=has_data,
            form_type='Schedule E',
            data=rental,
            confidence=0.7 if has_data else 0.0,
            warnings=warnings,
            source_file=document.file_path,
        )

    # ------------------------------------------------------------------
    # Composite 1099 (consolidated brokerage statements)
    # ------------------------------------------------------------------

    def is_composite_1099(self, text: str) -> bool:
        """Check if document is a composite/consolidated 1099 statement."""
        text_upper = text.upper()
        for indicator in self.COMPOSITE_INDICATORS:
            if indicator in text_upper:
                return True
        # Also detect by presence of multiple 1099 form types
        form_count = sum(
            1 for ft in ['1099-DIV', '1099-INT', '1099-B', '1099-MISC']
            if ft in text_upper
        )
        return form_count >= 2

    def extract_composite_1099(self, document: ParsedDocument) -> List[ExtractionResult]:
        """
        Extract multiple 1099 forms from a composite/consolidated statement.

        Composite brokerage statements (Fidelity, Schwab, Robinhood, Merrill)
        contain 1099-DIV, 1099-INT, and 1099-B sections in a single PDF.

        Returns:
            List of ExtractionResult, one per detected sub-form.
        """
        text = document.text_content
        text_upper = text.upper()
        results = []

        # Try to extract payer/broker name
        payer_name = self._extract_composite_payer(text)

        # --- 1099-DIV ---
        if '1099-DIV' in text_upper or 'DIVIDENDS AND DISTRIBUTIONS' in text_upper:
            div_result = self._extract_composite_div(text, payer_name)
            if div_result:
                results.append(div_result)

        # --- 1099-INT ---
        if '1099-INT' in text_upper or 'INTEREST INCOME' in text_upper:
            int_result = self._extract_composite_int(text, payer_name)
            if int_result:
                results.append(int_result)

        # --- 1099-MISC ---
        if '1099-MISC' in text_upper or 'MISCELLANEOUS' in text_upper:
            misc_result = self._extract_composite_misc(text, payer_name)
            if misc_result:
                results.append(misc_result)

        # --- 1099-B ---
        if '1099-B' in text_upper:
            b_results = self._extract_composite_b(text, payer_name, document.file_path)
            results.extend(b_results)

        return results

    @staticmethod
    def _extract_composite_payer(text: str) -> str:
        """Extract broker/payer name from a composite 1099 statement."""
        patterns = [
            r"PAYER.?S\s+(?:Name\s+and\s+)?Address[:\s]*\n([A-Z][A-Za-z\s&.,]+?)(?:\n|$)",
            r"\n(NATIONAL FINANCIAL SERVICES[A-Za-z\s,.]*)",
            r"\n(CHARLES SCHWAB[A-Za-z\s&,.]*)",
            r"(Merrill[\s\w]+(?:LLC|Inc\.?))",
            r"(Robinhood\s*(?:Securities|Markets)\s*(?:LLC|Inc\.?))",
            r"(JPMORGAN\s*(?:SECURITIES|BROKER)[A-Za-z\s,.]*(?:LLC|INC\.?))",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return "Composite 1099"

    def _extract_composite_div(self, text: str, payer_name: str) -> Optional[ExtractionResult]:
        """Extract 1099-DIV data from composite statement text."""
        # Patterns match across Fidelity (dotted), Robinhood (dash), ML/Schwab,
        # and Chase (no-space labels like "Totalordinarydividends").
        # Use finditer + sum to handle multi-account composites.
        ordinary = 0.0
        qualified = 0.0
        cap_gain = 0.0

        for m in re.finditer(
            r'1a[\s.,-]*Total\s*[Oo]rdinary\s*[Dd]ividends.*?([\d,]+\.\d{2})', text
        ):
            ordinary += self._parse_amount(m.group(1))

        for m in re.finditer(
            r'1b[\s.,-]*[Qq]ualified\s*[Dd]ividends.*?([\d,]+\.\d{2})', text
        ):
            qualified += self._parse_amount(m.group(1))

        for m in re.finditer(
            r'2a[\s.,-]*Total\s*[Cc]apital\s*[Gg]ain.*?([\d,]+\.\d{2})', text
        ):
            cap_gain += self._parse_amount(m.group(1))

        if ordinary <= 0:
            return None

        data = Form1099Div(
            payer_name=payer_name,
            ordinary_dividends=ordinary,
            qualified_dividends=qualified,
            capital_gain_distributions=cap_gain,
            federal_withheld=0.0,
        )
        return ExtractionResult(
            success=True,
            form_type='1099-DIV',
            data=data,
            confidence=0.8,
            warnings=[],
        )

    def _extract_composite_int(self, text: str, payer_name: str) -> Optional[ExtractionResult]:
        """Extract 1099-INT data from composite statement text."""
        interest_box1 = 0.0
        interest_box3 = 0.0  # U.S. Treasury interest

        # Box 1: Interest Income
        # Pattern avoids matching "1099-INT" header (requires space/dot/dash after "1")
        for m in re.finditer(
            r'(?:^|\s)1[\s.,-]+Interest\s*[Ii]ncome.*?([\d,]+\.\d{2})', text, re.MULTILINE
        ):
            interest_box1 += self._parse_amount(m.group(1))

        # Box 3: Interest on U.S. Savings Bonds and Treasury Obligations
        for m in re.finditer(
            r'3[\s.,-]+Interest\s*on\s*U\.?S\.?.*?(?:Treas|Treasury).*?([\d,]+\.\d{2})',
            text, re.IGNORECASE,
        ):
            interest_box3 += self._parse_amount(m.group(1))

        if interest_box1 <= 0 and interest_box3 <= 0:
            return None

        warnings = []
        if interest_box3 > 0:
            warnings.append(
                f"Includes ${interest_box3:,.2f} in U.S. Treasury interest (Box 3, state-exempt)"
            )

        data = Form1099Int(
            payer_name=payer_name,
            interest_income=interest_box1,
            us_treasury_interest=interest_box3,
            federal_withheld=0.0,
        )
        return ExtractionResult(
            success=True,
            form_type='1099-INT',
            data=data,
            confidence=0.8,
            warnings=warnings,
        )

    def _extract_composite_misc(self, text: str, payer_name: str) -> Optional[ExtractionResult]:
        """Extract 1099-MISC data from composite statement text."""
        other_income = 0.0

        # Box 3: Other income
        for m in re.finditer(
            r'3[\s.,-]*Other\s*[Ii]ncome.*?([\d,]+\.\d{2})', text
        ):
            other_income += self._parse_amount(m.group(1))

        if other_income <= 0:
            return None

        data = Form1099Misc(
            payer_name=payer_name,
            other_income=other_income,
            federal_withheld=0.0,
        )
        return ExtractionResult(
            success=True,
            form_type='1099-MISC',
            data=data,
            confidence=0.8,
            warnings=[],
        )

    def _extract_composite_b(
        self, text: str, payer_name: str, file_path: str
    ) -> List[ExtractionResult]:
        """Extract 1099-B summary from composite statement.

        Parses the "Summary of Proceeds From Broker and Barter Exchange
        Transactions" table found in Fidelity/Schwab/ML composite statements.
        Returns one ExtractionResult per category (short-term / long-term).

        Summary table row format (Fidelity):
          Short-term transactions for which basis is reported to the IRS
            <proceeds> <cost_basis> <market_discount> <wash_sales> <gain_loss> <fed_withheld>
        """
        results: List[ExtractionResult] = []

        # --- Fidelity/Schwab summary table rows ---
        # OCR often strips spaces within labels, producing text like:
        #   "Short-termtransactionsforwhichbasisisreportedtotheIRS 1,284,956.92 ..."
        # So we use \s* between words to handle both normal and no-space OCR.
        _SUMMARY_ROW = (
            r'({term})-term\s*transactions\s*for\s*which\s*basis\s*is\s*'
            r'(?:reported|not\s*reported)\s*to\s*the\s*IRS'
            r'(?:\s*and\s*Term\s*is\s*Unknown)?'
            r'\s+([\d,]+\.\d{{2}})'   # proceeds
            r'\s+([\d,]+\.\d{{2}})'   # cost basis
            r'\s+([\d,]+\.\d{{2}})'   # market discount
            r'\s+([\d,]+\.\d{{2}})'   # wash sales
            r'\s+(-?[\d,]+\.\d{{2}})' # gain/loss
            r'\s+([\d,]+\.\d{{2}})'   # fed withheld
        )

        # Accumulate short-term and long-term totals across all rows
        st_proceeds = st_basis = st_wash = st_gain = st_discount = 0.0
        lt_proceeds = lt_basis = lt_wash = lt_gain = lt_discount = 0.0

        for term, is_short in [('Short', True), ('Long', False)]:
            pat = _SUMMARY_ROW.format(term=term)
            for m in re.finditer(pat, text):
                p = self._parse_amount(m.group(2))
                b = self._parse_amount(m.group(3))
                md = self._parse_amount(m.group(4))
                ws = self._parse_amount(m.group(5))
                gl = self._parse_amount(m.group(6))
                if is_short:
                    st_proceeds += p
                    st_basis += b
                    st_discount += md
                    st_wash += ws
                    st_gain += gl
                else:
                    lt_proceeds += p
                    lt_basis += b
                    lt_discount += md
                    lt_wash += ws
                    lt_gain += gl

        # --- Fallback: Box A / Box D realized gain/loss lines ---
        # (Robinhood format and Fidelity per-section TOTALS pages)
        if st_proceeds == 0 and lt_proceeds == 0:
            for m in re.finditer(
                r'Box\s*([AD]).*?(?:Short|Long)-Term\s+Realized\s+'
                r'(?:Gain|Loss)\s+(-?[\d,]+\.\d{2})',
                text,
            ):
                val = self._parse_amount(m.group(2))
                if m.group(1) == 'A':
                    st_gain += val
                else:
                    lt_gain += val

        # Build results
        for label, is_short, proceeds, basis, discount, wash, gain in [
            ('Short-term', True, st_proceeds, st_basis, st_discount, st_wash, st_gain),
            ('Long-term', False, lt_proceeds, lt_basis, lt_discount, lt_wash, lt_gain),
        ]:
            if proceeds == 0 and basis == 0 and gain == 0:
                continue
            data = Form1099B(
                broker_name=payer_name,
                description=f"{label} summary",
                proceeds=proceeds,
                cost_basis=basis,
                gain_loss=gain,
                wash_sale_disallowed=wash,
                market_discount=discount,
                is_short_term=is_short,
                is_summary=True,
            )
            warnings = []
            if wash > 0:
                warnings.append(
                    f"{label} wash sale disallowed: ${wash:,.2f} "
                    f"(already included in cost basis)"
                )
            results.append(ExtractionResult(
                success=True,
                form_type='1099-B',
                data=data,
                confidence=0.8 if proceeds > 0 else 0.5,
                warnings=warnings,
            ))

        return results

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

        # Content-based detection first; folder hint as fallback for cases
        # where OCR/text is too poor for content matching.
        form_type = self.identify_form_type(document.text_content)
        if not form_type:
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
            return self.extract_1099_g(document)
        elif form_type == '1098-T':
            return self.extract_1098_t(document)
        elif form_type == '1099-B':
            # 1099-B is complex, return basic info
            return ExtractionResult(
                success=False,
                form_type='1099-B',
                data=None,
                confidence=0.0,
                warnings=[f"1099-B detected but requires manual review: {document.file_path}"]
            )
        elif form_type == '1099':
            # Generic 1099 folder — try text-based detection for sub-type
            detected = self.identify_form_type(document.text_content)
            if detected and detected.startswith('1099'):
                return self.extract(document, category_hint=detected)
            return ExtractionResult(
                success=False,
                form_type='1099',
                data=None,
                confidence=0.0,
                warnings=[f"1099 form in {document.file_path} — could not determine sub-type from content; requires manual review"]
            )
        elif form_type == '1099-MISC':
            return self.extract_1099_misc(document)
        elif form_type == 'Misc Deduction':
            return self.extract_misc_deduction(document)
        elif form_type == 'Schedule E':
            return self.extract_rental_pm_statement(document)
        elif form_type == 'Estimated Payment':
            return self.extract_estimated_payment(document)
        elif form_type == 'Vehicle Registration':
            return self.extract_vehicle_registration(document)
        elif form_type == 'Property Tax':
            return self.extract_property_tax(document, tax_year=self.tax_year)
        elif form_type == 'FSA':
            return self.extract_fsa(document)
        elif form_type == 'Charitable Contribution':
            return self.extract_charitable_contribution(document)
        elif form_type in ('Home Insurance', '529 Plan'):
            return ExtractionResult(
                success=True,
                form_type=form_type,
                data=DocumentOnly(category=form_type, description=form_type),
                confidence=0.5,
                warnings=[],
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

            # Composite 1099: extract multiple form types from one document.
            # Trigger on generic '1099' hint, or any 1099 sub-type hint when the
            # document text contains multiple form types (composite statement).
            is_1099_hint = hint and (hint == '1099' or hint.startswith('1099-'))
            if is_1099_hint and self.is_composite_1099(doc.text_content):
                composite_results = self.extract_composite_1099(doc)
                if composite_results:
                    for r in composite_results:
                        r.source_file = doc.file_path
                        r.source_text = doc.text_content
                        results.append(r)
                        safe_path = doc.file_path.encode('ascii', errors='replace').decode('ascii')
                        if r.success:
                            print(f"Extracted {r.form_type} from {safe_path} (composite)")
                        else:
                            print(f"  {r.form_type} in {safe_path}: {r.warnings}")
                    continue
                # Composite detected but nothing extracted — fall back to
                # single-form extraction (e.g. Chase 1099-INT with
                # boilerplate mentioning other form types)

            result = self.extract(doc, category_hint=hint)
            result.source_file = doc.file_path
            result.source_text = doc.text_content
            results.append(result)
            safe_path = doc.file_path.encode('ascii', errors='replace').decode('ascii')
            if result.success:
                print(f"Extracted {result.form_type} from {safe_path}")
            else:
                print(f"Could not extract data from {safe_path}: {result.warnings}")
        return results
