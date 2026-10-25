"""Smart leave (M8): natural-language -> pre-filled leave form JSON.

EMPLOYEE-ONLY, READ-ONLY: this module never writes anything. It either returns a
complete draft (endpoint sets ``requires_confirmation=true`` and the USER submits
``POST /api/leave/requests``) or a clarifying question (``requires_confirmation``
stays false and NO draft is returned).

Rules implemented here:
- Relative dates resolve against the REAL current date in the COMPANY timezone
  (passed in by the caller as `today`) - never against a guessed date.
- Ambiguity (missing dates, missing leave type, missing reason) -> question, never
  a silently guessed form.
- Leave type inference: wedding/family/party -> casual; sick/fever/doctor ->
  sick; vacation/annual -> annual; explicitly unpaid -> unpaid; conflicting
  signals or nothing -> ask.
- Roman Urdu basics: chutti/chhutti (leave), kal (tomorrow in leave context),
  parso (day after tomorrow), shadi (wedding), bukhar/doctor (sick), next week.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

LEAVE_INTENT = (
    "chutti",
    "chhutti",
    "day off",
    "days off",
    "off for",
    "off on",
    "take off",
    "need off",
    "apply for leave",
    "leave for",
    "need leave",
    "want leave",
    "leave chahiye",
    "leave chahta",
    "leave chahti",
    "i need off",
    "be off",
    "off next",
    "off this",
    "off tomorrow",
    "off on",
    "off for",
)
LEAVE_WORDS = ("chutti", "chhutti", "leave", "off")

# Messages that are QUESTIONS about leave, not requests (handled elsewhere).
_NOT_A_REQUEST = (
    "left",
    "remaining",
    "balance",
    "bachi",
    "bacha",
    "kitni",
    "kitna",
    "who is",
    "how many",
    "summary",
    "policy",
    "quota",
    "rule",
)

_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("sick", ("sick", "fever", "bukhar", "doctor", "hospital", "medical", "flu", "cold",
              "ill", "illness", "clinic", "tabiyat", "shugal")),
    ("casual", ("wedding", "shadi", "shaadi", "family", "party", "event", "nikah",
                "birthday", "casual", "function", "gathering")),
    ("annual", ("annual", "vacation", "holiday trip", "trip", "tour", "travel",
                "vacations")),
    ("unpaid", ("unpaid", "without pay", "bila tankhwah")),
]


@dataclass
class SmartLeaveDraft:
    """Complete draft (question is None) or clarification (payload fields None)."""

    type: str | None = None
    start: dt.date | None = None
    end: dt.date | None = None
    reason: str | None = None
    question: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.question is None and None not in (self.type, self.start, self.end, self.reason)

    def payload(self) -> dict | None:
        if not self.is_complete:
            return None
        return {
            "type": self.type,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reason": self.reason,
        }


def looks_like_leave_request(message: str) -> bool:
    text = " ".join(message.lower().split())
    if not text:
        return False
    if any(p in text for p in _NOT_A_REQUEST):
        return False
    has_word = any(w in text for w in LEAVE_WORDS)
    has_intent = any(p in text for p in LEAVE_INTENT)
    has_verb = any(
        v in text
        for v in ("i need", "i want", "i will be", "i'll be", "mujhe", "please",
                  "can i", "could i", "let me", "plan to", "going to", "chahiye")
    )
    return has_word and (has_intent or has_verb)


# --------------------------------------------------------------------- dates
def _shift_year(d: dt.date, today: dt.date) -> dt.date:
    """Bare day+month dates default to this year, next year when already past."""
    if d < today:
        try:
            return d.replace(year=today.year + 1)
        except ValueError:  # 29 Feb in a non-leap year
            return today
    return d


def _weekday_tokens(text: str) -> list[tuple[int, int, bool]]:
    """[(position, weekday_index, is_next)] in text order."""
    out: list[tuple[int, int, bool]] = []
    pattern = re.compile(
        r"\b(next|coming|agla|aane wala)?\s*"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b"
    )
    for m in pattern.finditer(text):
        name = m.group(2)
        for idx, full in enumerate(WEEKDAYS):
            if name == full or name.startswith(full[:3]):
                out.append((m.start(), idx, bool(m.group(1))))
                break
    return out


def _extract_dates(text: str, today: dt.date) -> list[dt.date]:
    """All mentioned dates, resolved in the order they appear in the sentence.

    First token resolves against `today`; every later token resolves against the
    previously resolved date (so "next Monday and Tuesday" = Mon..Tue).
    """
    tokens: list[tuple[int, str, object]] = []  # (position, kind, value)

    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        try:
            tokens.append((m.start(), "date", dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            continue

    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?\b", text):
        month = MONTHS.get(m.group(2))
        if month:
            try:
                d = dt.date(today.year, month, int(m.group(1)))
                tokens.append((m.start(), "date", _shift_year(d, today)))
            except ValueError:
                continue

    for m in re.finditer(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", text):
        month = MONTHS.get(m.group(1))
        if month:
            try:
                d = dt.date(today.year, month, int(m.group(2)))
                tokens.append((m.start(), "date", _shift_year(d, today)))
            except ValueError:
                continue

    if "day after tomorrow" in text or "parso" in text:
        tokens.append((5_000, "date", today + dt.timedelta(days=2)))
    elif re.search(r"\btomorrow\b", text) or re.search(r"\bkal\b", text):
        tokens.append((5_000, "date", today + dt.timedelta(days=1)))

    for pos, wd_idx, is_next in _weekday_tokens(text):
        tokens.append((pos, "weekday", (wd_idx, is_next)))

    if not tokens and "next week" in text:
        # "next week" -> Monday..Friday of the next calendar week (documented).
        monday = today + dt.timedelta(days=((0 - today.weekday()) % 7) or 7)
        return [monday, monday + dt.timedelta(days=4)]

    tokens.sort(key=lambda item: item[0])

    resolved: list[dt.date] = []
    for _, kind, value in tokens:
        if kind == "date":
            resolved.append(value)
            continue
        wd_idx, is_next = value
        base = resolved[-1] if resolved else today
        delta = (wd_idx - base.weekday()) % 7
        if delta == 0:
            delta = 7 if (is_next or resolved) else 0  # bare & first token = today
        resolved.append(base + dt.timedelta(days=delta))

    unique: list[dt.date] = []
    for d in resolved:
        if d not in unique:
            unique.append(d)
    return unique


def _infer_type(text: str) -> str | None:
    hits = {code for code, words in _TYPE_KEYWORDS if any(w in text for w in words)}
    if len(hits) == 1:
        return hits.pop()
    return None  # none, or conflicting -> ask


def _extract_reason(text: str) -> str | None:
    m = re.search(r"\bfor\s+(.+)$", text)
    if m:
        reason = m.group(1).strip(" .,!?")
        reason = re.sub(r"^(a|an|the)\s+", "", reason)
        if reason:
            return reason[:500]
    for marker in ("ki wajah se", "ki waja se", "ki wajah", "ke liye"):
        idx = text.find(marker)
        if idx > 0:
            words = text[:idx].split()[-4:]
            reason = " ".join(words).strip(" .,!?")
            if reason:
                return reason[:500]
    return None


def parse_leave_request(message: str, today: dt.date) -> SmartLeaveDraft:
    """Parse a leave sentence. Never guesses: missing dates / type / reason each
    produce a clarifying question instead of a partial payload."""
    text = " ".join(message.lower().split())
    dates = _extract_dates(text, today)

    if not dates:
        return SmartLeaveDraft(
            question=(
                "Which dates do you need off? Tell me something like "
                "\"next Monday and Tuesday\" or a specific date (YYYY-MM-DD)."
            )
        )
    start, end = dates[0], dates[-1]
    if end < start:
        end = start

    ltype = _infer_type(text)
    if ltype is None:
        conflict = {
            code for code, words in _TYPE_KEYWORDS if any(w in text for w in words)
        }
        if len(conflict) > 1:
            options = ", ".join(sorted(conflict))
            return SmartLeaveDraft(
                start=start, end=end,
                question=f"That mentions more than one kind of leave ({options}). Which type should I use?",
            )
        return SmartLeaveDraft(
            start=start, end=end,
            question=(
                "Which leave type should I use - annual, sick or casual? "
                "(For example: \"casual leave for a wedding\".)"
            ),
        )

    reason = _extract_reason(text)
    if not reason:
        return SmartLeaveDraft(
            type=ltype, start=start, end=end,
            question="What is the reason for the leave? (For example: wedding, medical appointment.)",
        )

    return SmartLeaveDraft(type=ltype, start=start, end=end, reason=reason)
