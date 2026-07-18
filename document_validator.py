"""
document_validator.py  —  FinScore AI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Robust PDF/CSV validation with:
  • Text-based PDF extraction  (pdfplumber)
  • Image/Scanned PDF OCR      (pytesseract + pdf2image)
  • Password-protected detection
  • Diagnostic logging per page
  • Expanded bank + transaction pattern matching
  • 100-point confidence scoring (pass >= 60)

Scoring rubric:
  Bank name found        → 25 pts
  Account number found   → 20 pts
  IFSC code found        → 10 pts
  Transaction keywords   → 25 pts
  Debit/Credit columns   → 10 pts
  Date patterns found    → 10 pts
  ─────────────────────────────────
  Pass threshold         → 60 pts  (lowered from 70 for real PDFs)
"""

import re
import os
import logging
import pandas as pd
import pdfplumber

# ── OCR imports (optional — graceful fallback if not installed) ───────────────
OCR_AVAILABLE    = False
POPPLER_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    import io

    # Common Tesseract install paths on Windows
    _TESS_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(
            os.environ.get("USERNAME", "")
        ),
        r"C:\tools\tesseract\tesseract.exe",
    ]
    for _p in _TESS_PATHS:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            OCR_AVAILABLE = True
            break

    if not OCR_AVAILABLE:
        # Try system PATH
        import shutil
        if shutil.which("tesseract"):
            OCR_AVAILABLE = True

except ImportError:
    pass

try:
    from pdf2image import convert_from_path
    POPPLER_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger("finscore.validator")

# ── Scoring ───────────────────────────────────────────────────────────────────
PASS_SCORE       = 60   # lowered from 70 — real PDFs often lack IFSC in text
MIN_TXN_KEYWORDS = 3

# ── Indian bank names ─────────────────────────────────────────────────────────
BANK_NAMES = [
    "state bank of india","sbi","sbi bank",
    "hdfc bank","hdfc",
    "icici bank","icici",
    "axis bank","axis",
    "kotak mahindra bank","kotak mahindra","kotak",
    "canara bank",
    "bank of baroda","bob",
    "punjab national bank","pnb",
    "union bank of india","union bank",
    "bank of india","boi",
    "indian bank",
    "central bank of india","central bank",
    "yes bank",
    "idfc first bank","idfc first","idfc",
    "indusind bank","indusind",
    "federal bank",
    "south indian bank",
    "karnataka bank",
    "bandhan bank",
    "rbl bank","rbl",
    "city union bank",
    "dcb bank","dcb",
    "saraswat bank",
    "airtel payments bank",
    "paytm payments bank",
    "fino payments bank",
    "au small finance bank","au bank",
    "equitas small finance bank",
    "ujjivan small finance bank",
    "jana small finance bank",
    "esaf small finance bank",
    "nainital bank",
    "jammu and kashmir bank","j&k bank",
    "karur vysya bank","kvb",
    "tamilnad mercantile bank","tmb",
    "lakshmi vilas bank",
    "abhyudaya bank",
    "bassein catholic bank",
    "bharat cooperative bank",
    "dhan laxmi bank",
    "the catholic syrian bank",
    "the dhanalakshmi bank",
]

# ── Transaction keywords — expanded ──────────────────────────────────────────
# Each group maps to a transaction type
TXN_INCOME_KW = re.compile(
    r"\b(sal\s*cr|salary\s*cr(?:edit)?|salary\s*credit|sal\s*credit|"
    r"ach\s*cr(?:edit)?|neft\s*cr(?:edit)?|neft\s*in|imps\s*cr(?:edit)?|"
    r"upi\s*cr(?:edit)?|rtgs\s*cr(?:edit)?|by\s*transfer|cash\s*deposit|"
    r"fd\s*maturity|interest\s*credit|dividend|bonus\s*credit|"
    r"refund\s*credit|reversal\s*credit|cashback|ach\s*credit|"
    r"credited|credit\s*transfer|opening\s*balance|deposit)\b",
    re.IGNORECASE,
)

TXN_EXPENSE_KW = re.compile(
    r"\b(dr|debit|neft\s*dr|imps\s*dr|upi\s*dr|rtgs\s*dr|ach\s*dr|"
    r"atm\s*wd|atm\s*withdrawal|cash\s*withdrawal|withdrawal|"
    r"emi\s*debit|emi|loan\s*emi|standing\s*instruction|si\s*debit|"
    r"nach\s*debit|nach|ecs\s*debit|ecs|bill\s*payment|"
    r"utility\s*payment|electricity|water\s*bill|gas\s*bill|"
    r"internet\s*bill|recharge|insurance\s*premium|"
    r"debited|purchase|pos|swipe|shopping|amazon|flipkart|"
    r"swiggy|zomato|uber|ola|paytm|gpay|phonepe)\b",
    re.IGNORECASE,
)

TXN_GENERAL_KW = re.compile(
    r"\b(neft|imps|upi|rtgs|atm|ecs|nach|emi|salary|transfer|payment|"
    r"purchase|withdrawal|deposit|credited|debited|cashback|refund|"
    r"recharge|bill|mandate|bounced|reversed|cheque|chq|clearing|"
    r"standing\s*order|auto\s*debit|inward|outward|remittance|"
    r"dd|demand\s*draft|mis|recurring|rd|ppf|nsc|mutual\s*fund|"
    r"sip|trading|broker|dividend|interest|charges|penalty|"
    r"gst|tds|tax)\b",
    re.IGNORECASE,
)

# ── Pattern matchers ──────────────────────────────────────────────────────────
RE_ACCOUNT = re.compile(
    r"(?:a/?c|account|acc|ac)[\s\.\:\-#]*([xX*]{0,8}\d{4,18})"
    r"|(?<!\d)(\d{9,18})(?!\d)",
    re.IGNORECASE,
)
RE_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", re.IGNORECASE)
RE_AMOUNT = re.compile(
    r"(?:rs\.?\s*|inr\s*|₹\s*)?(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d{4,}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
RE_DATE = re.compile(
    r"\b(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}"
    r"|\d{4}[-/\.]\d{2}[-/\.]\d{2}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4})\b",
    re.IGNORECASE,
)
RE_BALANCE = re.compile(
    r"(?:opening|closing|available|current|ledger)?\s*bal(?:ance)?[\s\:\-]*"
    r"(?:rs\.?\s*|₹\s*)?(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
RE_STATEMENT_PERIOD = re.compile(
    r"(?:statement|period|from|to)[\s\:\-]*"
    r"(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})",
    re.IGNORECASE,
)
RE_DEBIT_CREDIT_HDR = re.compile(
    r"\b(debit|credit|dr\.?|cr\.?|withdrawal|deposit|"
    r"amount|balance|particulars|narration|description|"
    r"transaction|txn|value\s*date|chq|ref)\b",
    re.IGNORECASE,
)

# ── Rejection keywords ────────────────────────────────────────────────────────
REJECT_KW = re.compile(
    r"\b(aadhaar|aadhar|uid\s*number|pan\s*card|passport\s*number|"
    r"driving\s*licen[sc]e|voter\s*id|curriculum\s*vitae|\bcv\b|"
    r"resume\b|certificate\s*of|gst\s*invoice|purchase\s*order|"
    r"admit\s*card|hall\s*ticket|payslip|pay\s*slip|salary\s*slip|"
    r"offer\s*letter|appointment\s*letter|experience\s*letter|"
    r"marksheet|mark\s*sheet|grade\s*card)\b",
    re.IGNORECASE,
)


# ═════════════════════════════════════════════════════════════════════════════
# PDF TEXT EXTRACTION  (text-based + OCR fallback)
# ═════════════════════════════════════════════════════════════════════════════

def extract_pdf_text(filepath: str, pdf_password: str = None) -> dict:
    """
    Extract all text from a PDF with full diagnostics.

    Returns:
    {
      pdf_type:    'text' | 'image' | 'password' | 'empty',
      full_text:   str,
      page_count:  int,
      pages:       [ {page_num, char_count, text} ],
      ocr_used:    bool,
      error:       str | None,
    }
    """
    result = {
        "pdf_type":   "text",
        "full_text":  "",
        "page_count": 0,
        "pages":      [],
        "ocr_used":   False,
        "error":      None,
    }

    # ── 1. Try pdfplumber (text PDF) ──────────────────────────────────────────
    try:
        with pdfplumber.open(filepath, password=pdf_password or "") as pdf:
            result["page_count"] = len(pdf.pages)
            pages_text = []

            for i, page in enumerate(pdf.pages):
                page_info = {"page_num": i + 1, "char_count": 0, "text": ""}

                # Try table extraction first
                tables = page.extract_tables() or []
                table_text = ""
                for table in tables:
                    for row in table:
                        row_str = "  ".join(str(c).strip() for c in row if c)
                        if row_str.strip():
                            table_text += row_str + "\n"

                # Then raw text
                raw = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

                combined = (table_text + "\n" + raw).strip()
                page_info["text"]       = combined
                page_info["char_count"] = len(combined)
                pages_text.append(page_info)

                logger.debug(f"Page {i+1}: {len(combined)} chars extracted")

            result["pages"]     = pages_text
            result["full_text"] = "\n".join(p["text"] for p in pages_text)

    except Exception as e:
        err = str(e).lower()
        if "password" in err or "encrypt" in err or "pdfread" in err or "notimplemented" in err:
            result["pdf_type"] = "password"
            result["error"]    = "PDF is password-protected."
            return result
        result["error"] = str(e)

    # ── 2. Check if text was extracted ───────────────────────────────────────
    total_chars = len(result["full_text"].strip())

    if total_chars >= 50:
        result["pdf_type"] = "text"
        logger.debug(f"Text PDF: {total_chars} total chars extracted")
        return result

    # ── 3. Fallback → OCR ────────────────────────────────────────────────────
    result["pdf_type"] = "image"
    logger.debug("Low text content — attempting OCR...")

    if not OCR_AVAILABLE:
        result["error"] = (
            "Scanned or image-based PDF detected. "
            "OCR processing requires Tesseract. "
            "Please install Tesseract OCR from: "
            "https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return result

    if not POPPLER_AVAILABLE:
        result["error"] = (
            "Scanned PDF detected. pdf2image/poppler not available for OCR. "
            "Please install poppler: https://github.com/oschwartz10612/poppler-windows"
        )
        return result

    try:
        images = convert_from_path(filepath, dpi=200)
        ocr_pages = []
        full_ocr  = []

        for i, img in enumerate(images):
            ocr_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
            page_info = {
                "page_num":   i + 1,
                "char_count": len(ocr_text),
                "text":       ocr_text,
            }
            ocr_pages.append(page_info)
            full_ocr.append(ocr_text)
            logger.debug(f"OCR Page {i+1}: {len(ocr_text)} chars")

        result["pages"]     = ocr_pages
        result["full_text"] = "\n".join(full_ocr)
        result["ocr_used"]  = True
        result["page_count"]= len(images)

        if not result["full_text"].strip():
            result["error"] = "OCR produced no text. Image quality may be too low."

    except Exception as e:
        result["error"] = f"OCR failed: {e}"

    return result


# ═════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ═════════════════════════════════════════════════════════════════════════════

def _score_text(text: str, pdf_info: dict = None) -> dict:
    """
    Score text content against all bank statement heuristics.
    Returns full breakdown dict.
    """
    t_lower = text.lower()
    score   = 0
    reasons = []
    details = {}

    # ── 0. Rejection check ───────────────────────────────────────────────────
    rej = REJECT_KW.search(text)
    if rej:
        return {
            "score": 0, "bank_name": None,
            "has_account": False, "has_ifsc": False,
            "txn_count": 0, "has_debit_credit": False,
            "rejection_flag": rej.group(0),
            "reasons": [f"✗ Document is a '{rej.group(0)}', not a bank statement."],
            "details": {},
        }

    # ── 1. Bank name (25 pts) ────────────────────────────────────────────────
    found_bank = None
    for bank in BANK_NAMES:
        if bank in t_lower:
            found_bank = bank.title()
            score += 25
            reasons.append(f"✓ Bank detected: {found_bank}")
            break
    if not found_bank:
        # partial match — look for "bank" keyword at all
        if "bank" in t_lower or "banking" in t_lower:
            score += 10
            reasons.append("~ 'Bank' keyword found but no specific bank name matched (+10 pts).")
        else:
            reasons.append("✗ No recognised bank name found.")

    # ── 2. Account number (20 pts) ───────────────────────────────────────────
    acct_matches = []
    for m in RE_ACCOUNT.finditer(text):
        acct = (m.group(1) or m.group(2) or "").replace(" ", "")
        digits = re.sub(r"[^0-9]", "", acct)
        if 9 <= len(digits) <= 18:
            acct_matches.append(acct)

    has_account = len(acct_matches) > 0
    if has_account:
        score += 20
        sample = re.sub(r"\d", "X", acct_matches[0])[-8:]
        reasons.append(f"✓ Account number detected (XXXXXXXX{sample[-4:]}).")
    else:
        reasons.append("✗ No account number pattern found.")

    details["acct_matches"] = len(acct_matches)

    # ── 3. IFSC code (10 pts) ────────────────────────────────────────────────
    ifsc_matches = RE_IFSC.findall(text)
    has_ifsc     = len(ifsc_matches) > 0
    if has_ifsc:
        score += 10
        reasons.append(f"✓ IFSC code detected: {ifsc_matches[0].upper()}")
    else:
        reasons.append("✗ No IFSC code found (optional for some statements).")

    details["ifsc_found"] = ifsc_matches[0].upper() if ifsc_matches else None

    # ── 4. Transaction keywords (25 pts) ────────────────────────────────────
    income_hits  = TXN_INCOME_KW.findall(text)
    expense_hits = TXN_EXPENSE_KW.findall(text)
    general_hits = TXN_GENERAL_KW.findall(text)
    date_hits    = RE_DATE.findall(text)
    amount_hits  = RE_AMOUNT.findall(text)

    # Count unique keywords
    income_count  = len(income_hits)
    expense_count = len(expense_hits)
    general_count = len(set(h.lower() for h in general_hits))
    date_count    = len(date_hits)
    amount_count  = len(amount_hits)

    # Estimate transaction rows
    txn_count = max(
        min(date_count, amount_count),   # date + amount pairs
        income_count + expense_count,     # income + expense keywords
        general_count,                    # general transaction keywords
    )

    details["income_hits"]  = income_count
    details["expense_hits"] = expense_count
    details["date_hits"]    = date_count
    details["amount_hits"]  = amount_count
    details["txn_count"]    = txn_count

    if txn_count >= 10:
        score += 25
        reasons.append(f"✓ {txn_count}+ transaction patterns detected.")
    elif txn_count >= MIN_TXN_KEYWORDS:
        pts = max(5, int(25 * txn_count / 10))
        score += pts
        reasons.append(f"✓ {txn_count} transaction patterns detected (+{pts} pts).")
    elif income_count + expense_count >= 1:
        score += 8
        reasons.append(f"~ Some financial keywords found (+8 pts).")
    else:
        reasons.append(f"✗ No transaction keywords found ({txn_count} detected).")

    # ── 5. Debit/Credit column headers (10 pts) ──────────────────────────────
    dc_hits  = RE_DEBIT_CREDIT_HDR.findall(text)
    dc_uniq  = set(h.lower().strip() for h in dc_hits)
    has_dc   = len(dc_uniq) >= 2
    if has_dc:
        score += 10
        reasons.append(f"✓ Financial table headers detected: {', '.join(list(dc_uniq)[:5])}")
    else:
        reasons.append("✗ Debit/Credit table headers not clearly found.")

    # ── 6. Date patterns (10 pts) ────────────────────────────────────────────
    if date_count >= 5:
        score += 10
        reasons.append(f"✓ {date_count} date entries found.")
    elif date_count >= 2:
        score += 5
        reasons.append(f"~ {date_count} date entries found (+5 pts).")
    else:
        reasons.append(f"✗ Only {date_count} date entries found.")

    # ── Extra: Opening/Closing balance ───────────────────────────────────────
    balance_hits = RE_BALANCE.findall(text)
    if balance_hits:
        details["balance_found"] = balance_hits[:2]
        reasons.append(f"✓ Balance information detected.")

    # ── Extra: Statement period ──────────────────────────────────────────────
    period_hits = RE_STATEMENT_PERIOD.findall(text)
    if period_hits:
        details["statement_period"] = period_hits[:2]
        reasons.append(f"✓ Statement period detected.")

    # ── Diagnostic from PDF extraction ───────────────────────────────────────
    if pdf_info:
        details["page_count"]     = pdf_info.get("page_count", 0)
        details["pdf_type"]       = pdf_info.get("pdf_type", "unknown")
        details["ocr_used"]       = pdf_info.get("ocr_used", False)
        details["page_breakdown"] = [
            {"page": p["page_num"], "chars": p["char_count"]}
            for p in pdf_info.get("pages", [])
        ]

    return {
        "score":           min(score, 100),
        "bank_name":       found_bank,
        "has_account":     has_account,
        "has_ifsc":        has_ifsc,
        "txn_count":       txn_count,
        "has_debit_credit":has_dc,
        "rejection_flag":  None,
        "reasons":         reasons,
        "details":         details,
        "raw_text_sample": text[:2000],
    }


def _score_csv(df: pd.DataFrame) -> dict:
    """Score a parsed CSV DataFrame."""
    cols_lower = [c.lower() for c in df.columns]
    full_text  = " ".join(cols_lower) + "\n" + df.to_string()
    score      = 0
    reasons    = []
    details    = {"columns": cols_lower}

    rej = REJECT_KW.search(" ".join(cols_lower))
    if rej:
        return {
            "score": 0, "bank_name": None,
            "has_account": False, "has_ifsc": False,
            "txn_count": 0, "has_debit_credit": False,
            "rejection_flag": rej.group(0),
            "reasons": [f"✗ CSV is a '{rej.group(0)}', not a bank statement."],
            "details": details,
        }

    sample = full_text[:5000].lower()

    # Bank name
    found_bank = None
    for bank in BANK_NAMES:
        if bank in sample:
            found_bank = bank.title()
            score += 25
            reasons.append(f"✓ Bank detected: {found_bank}")
            break
    if not found_bank:
        if "bank" in sample:
            score += 10
            reasons.append("~ 'Bank' keyword found (+10 pts).")
        else:
            reasons.append("✗ No bank name found.")

    # Account column
    has_account = any(k in " ".join(cols_lower)
                      for k in ["account","acct","acc_no","a/c"])
    if has_account:
        score += 20
        reasons.append("✓ Account number column found.")
    else:
        reasons.append("✗ No account column found.")

    # IFSC
    ifsc = RE_IFSC.search(full_text[:8000])
    has_ifsc = bool(ifsc)
    if has_ifsc:
        score += 10
        reasons.append(f"✓ IFSC detected: {ifsc.group(0).upper()}")
    else:
        reasons.append("✗ No IFSC found.")

    # Rows
    txn_count = len(df)
    if txn_count >= 10:
        score += 25
        reasons.append(f"✓ {txn_count} transaction rows.")
    elif txn_count >= MIN_TXN_KEYWORDS:
        pts = max(5, int(25 * txn_count / 10))
        score += pts
        reasons.append(f"✓ {txn_count} rows (+{pts} pts).")
    else:
        reasons.append(f"✗ Only {txn_count} rows found.")

    details["txn_count"] = txn_count

    # Debit/credit columns
    dc_cols = [c for c in cols_lower if any(k in c for k in
               ["debit","credit","dr","cr","amount","withdrawal","deposit","balance"])]
    has_dc = len(dc_cols) >= 2
    if has_dc:
        score += 10
        reasons.append(f"✓ Financial columns: {', '.join(dc_cols[:4])}")
    else:
        reasons.append("✗ No debit/credit columns found.")

    # Date column
    date_cols = [c for c in cols_lower if any(k in c for k in ["date","dt","time","posted"])]
    if date_cols:
        score += 10
        reasons.append(f"✓ Date column detected: {date_cols[0]}")
    else:
        reasons.append("✗ No date column found.")

    return {
        "score":           min(score, 100),
        "bank_name":       found_bank,
        "has_account":     has_account,
        "has_ifsc":        has_ifsc,
        "txn_count":       txn_count,
        "has_debit_credit":has_dc,
        "rejection_flag":  None,
        "reasons":         reasons,
        "details":         details,
        "raw_text_sample": df.head(10).to_string(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def validate_document(filepath: str, ext: str, pdf_password: str = None) -> dict:
    """
    Main entry point. Called before any ML prediction.

    Returns dict with keys:
      valid, score, bank_name, txn_count, reasons,
      details, error_msg, raw_text, pdf_type, ocr_used
    """
    try:
        if ext == "pdf":
            pdf_info = extract_pdf_text(filepath, pdf_password=pdf_password)
            raw_text = pdf_info["full_text"]

            # Password protected
            if pdf_info["pdf_type"] == "password":
                return {
                    "valid": False,
                    "score": 0,
                    "bank_name": None,
                    "txn_count": 0,
                    "reasons": ["✗ PDF is password-protected."],
                    "details": {"pdf_type": "password"},
                    "error_msg": "This PDF is password-protected. Please enter the PDF password to continue.",
                    "raw_text": "",
                    "pdf_type": "password",
                    "ocr_used": False,
                    "password_required": True,
                }

            # No text at all and OCR not available
            if not raw_text.strip() and pdf_info["pdf_type"] == "image":
                err = pdf_info.get("error") or (
                    "Scanned or image-based PDF detected. "
                    "Install Tesseract OCR for automatic text extraction. "
                    "Download: https://github.com/UB-Mannheim/tesseract/wiki"
                )
                return _fail(
                    0,
                    ["✗ Scanned/image PDF — no text extractable without OCR."],
                    err,
                    {"pdf_type": "image", "ocr_available": OCR_AVAILABLE},
                    "", False
                )

            # No text even after OCR attempt
            if not raw_text.strip():
                return _fail(
                    0,
                    ["✗ No text could be extracted from this PDF."],
                    "No readable text found. The PDF may be corrupted or purely graphical.",
                    pdf_info, "", pdf_info.get("ocr_used", False)
                )

            result = _score_text(raw_text, pdf_info)

        elif ext == "csv":
            try:
                df = pd.read_csv(filepath)
                df.columns = [c.strip().lower() for c in df.columns]
            except Exception as e:
                return _fail(0, [f"✗ CSV error: {e}"], f"CSV parse error: {e}", {}, "", False)
            result = _score_csv(df)
            pdf_info = {"pdf_type": "csv", "ocr_used": False}

        else:
            return _fail(0, ["✗ Unsupported file type."],
                         "Only PDF and CSV accepted.", {}, "", False)

    except Exception as e:
        return _fail(0, [f"✗ Validation error: {e}"],
                     f"Unexpected error: {e}", {}, "", False)

    score = result["score"]
    valid = score >= PASS_SCORE and result["rejection_flag"] is None

    if result["rejection_flag"]:
        error_msg = (
            f"Document appears to be a '{result['rejection_flag']}'. "
            "Please upload a genuine bank statement."
        )
    elif not valid:
        error_msg = (
            f"Validation failed (score {score}/100, minimum {PASS_SCORE}). "
            "The file does not appear to be a bank statement. "
            "Ensure it contains account number, transactions, and bank name."
        )
    else:
        error_msg = ""

    return {
        "valid":            valid,
        "score":            score,
        "bank_name":        result["bank_name"],
        "txn_count":        result["txn_count"],
        "reasons":          result["reasons"],
        "details":          result["details"],
        "error_msg":        error_msg,
        "raw_text":         result.get("raw_text_sample", ""),
        "pdf_type":         (pdf_info or {}).get("pdf_type", "unknown"),
        "ocr_used":         (pdf_info or {}).get("ocr_used", False),
        "password_required": False,
    }


def _fail(score, reasons, error_msg, details, raw_text="", ocr_used=False):
    return {
        "valid":     False,
        "score":     score,
        "bank_name": None,
        "txn_count": 0,
        "reasons":   reasons,
        "details":   details,
        "error_msg": error_msg,
        "raw_text":  raw_text,
        "pdf_type":  details.get("pdf_type", "unknown") if isinstance(details, dict) else "unknown",
        "ocr_used":  ocr_used,
    }
