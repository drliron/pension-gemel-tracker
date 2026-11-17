"""סוכן קליטה וחילוץ (Document Parser Agent).

סדר פעולות קבוע: קריאת בייטים -> חילוץ טקסט -> מחיקת מזהים -> בחירת תבנית -> חילוץ שדות.
הבייטים המקוריים לא נשמרים; נשמר רק hash שלהם. טקסט גולמי לא נכנס ללוג ולא נשמר.
"""
from __future__ import annotations

import hashlib
import io

from ..parsers import pick_parser
from ..redact import redact_text


class IngestError(ValueError):
    pass


def _text_from_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - תלוי בסביבה
        raise IngestError("חסרה הספרייה pypdf לקריאת PDF") from exc
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _text_from_bytes(raw: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf") or raw[:5] == b"%PDF-":
        return _text_from_pdf(raw)
    for enc in ("utf-8-sig", "cp1255"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise IngestError("לא ניתן לפענח את הקובץ")


def ingest(raw: bytes, filename: str) -> dict:
    """מחזיר מילון חילוץ מוכן לשמירה כ-Statement במצב user_confirmed=False.

    הטקסט הנקי מוחזר לשימוש המסך לאימות בלבד (בזיכרון, לא נשמר).
    """
    if not raw:
        raise IngestError("הקובץ ריק")
    sha = hashlib.sha256(raw).hexdigest()
    text = _text_from_bytes(raw, filename)
    del raw  # אין צורך בבייטים המקוריים מכאן והלאה

    # צעד ראשון מוחלט על הטקסט: מחיקת מזהים לפני כל שימוש אחר
    clean, report = redact_text(text)
    del text

    module = pick_parser(clean)
    if module is None:
        return {
            "source_sha256": sha,
            "parser": None,
            "fields": {},
            "confidence": 0.0,
            "warnings": ["לא זוהתה תבנית מוכרת לדוח. אפשר להזין ידנית או לייבא CSV."],
            "redactions": report.counts,
            "clean_text": clean,
        }

    result = module.parse(clean)
    return {
        "source_sha256": sha,
        "parser": {"name": result.parser_name, "version": result.parser_version},
        "fields": result.fields,
        "confidence": result.confidence,
        "warnings": result.warnings,
        "redactions": report.counts,
        "clean_text": clean,
    }
