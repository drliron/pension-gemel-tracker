"""שלב 0 בצנרת: מחיקת מזהים אישיים לפני כל עיבוד אחר.

הכלל: שום טקסט מדוח לא עובר לשלב הבא לפני שעבר כאן. הפונקציה מחזירה טקסט נקי
וספירה של כל סוג מחיקה. הספירה נשמרת ב-Statement (לא הטקסט עצמו).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# תווית + מספר תעודת זהות (עד 9 ספרות, עם רווחים/מקפים/נקודות בתוכו)
ID_LABELED = re.compile(
    r"(מספר[ \t]*זהות|מס[\'׳]?[ \t]*זהות|ת\.?[ \t]*ז\.?|ת\"ז|ת״ז|תעודת[ \t]*זהות|מספר[ \t]*ת\.?ז\.?|דרכון)"
    r"[ \t]*[:\-]?[ \t]*(\d(?:[ \t\-./]{0,2}\d){4,8})"
)
# מספר בן 9 ספרות בודד (ת"ז שנדבקה למספר אחר בחילוץ מ-PDF)
NINE_DIGITS = re.compile(r"(?<![\d,.])\d{9}(?![\d,.])")
# ת"ז עם נקודות או לוכסנים
ID_SEPARATED = re.compile(r"(?<![\d,.])\d{1,4}(?:[./]\d{1,4}){2,3}(?![\d,]|[./]\d)")
# מספר חשבון ובנק / סניף
ACCOUNT_LABELED = re.compile(
    r"(מספר[ \t]*חשבון|מס[\'׳]?[ \t]*חשבון|חשבון[ \t]*בנק|מספר[ \t]*סניף|מספר[ \t]*פוליסה|מס[\'׳]?[ \t]*פוליסה)"
    r"[ \t]*[:\-]?[ \t]*([\d][\d \t\-/]{2,24})"
)
# שורת שם מלא: "שם: ..." / "שם מלא: ..." / "שם המבוטח: ..." / "שם העמית: ..."
NAME_LINE = re.compile(r"^(שם(?:[ \t]+המבוטח|[ \t]+העמית|[ \t]+מלא)?)[ \t]*[:\-][ \t]*.+$", re.MULTILINE)


@dataclass
class RedactionReport:
    counts: dict[str, int] = field(default_factory=lambda: {"id": 0, "account": 0, "name": 0})

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact_text(text: str) -> tuple[str, RedactionReport]:
    """מחזיר (טקסט נקי, דוח מחיקות). לא מדפיס ולא שומר את המקור."""
    report = RedactionReport()

    def _sub(pattern: re.Pattern, repl: str, key: str, s: str, group_pos: int | None = None) -> str:
        def _f(m: re.Match) -> str:
            report.counts[key] += 1
            if group_pos is None:
                return repl
            # שמור את התווית, מחק רק את הערך
            return m.group(0).replace(m.group(group_pos), repl)

        return pattern.sub(_f, s)

    text = _sub(NAME_LINE, "[שם הוסר]", "name", text)
    text = _sub(ID_LABELED, "[ת.ז. הוסרה]", "id", text, group_pos=2)
    text = _sub(ACCOUNT_LABELED, "[חשבון הוסר]", "account", text, group_pos=2)
    text = _sub(ID_SEPARATED, "[ת.ז. הוסרה]", "id", text)
    text = _sub(NINE_DIGITS, "[ת.ז. הוסרה]", "id", text)
    return text, report
