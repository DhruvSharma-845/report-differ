"""
PII redaction engine.

Uses deterministic regex patterns to detect and mask personally identifiable
information.  No ML models — fast, predictable, and auditable.

Covered PII categories
----------------------
- Social Security Numbers  (XXX-XX-XXXX and variants)
- Email addresses
- Phone numbers            (US 10/11-digit patterns)
- Credit / debit card numbers (13-19 digit Luhn-eligible sequences)
- IP addresses             (IPv4)
- Dates of birth           (common date formats)
- US street addresses      (number + street keyword heuristic)
- Person-name-like tokens adjacent to "name" labels (e.g. "Name: John Doe")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

PLACEHOLDER = "[REDACTED]"


@dataclass
class RedactionHit:
    category: str
    original: str
    start: int
    end: int


# Order matters: longer / more specific patterns first to avoid partial matches.
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("SSN", re.compile(
        r"\b\d{3}[-–]\d{2}[-–]\d{4}\b"
    )),
    ("CREDIT_CARD", re.compile(
        r"\b(?:\d[ -]*?){13,19}\b"
    )),
    ("EMAIL", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    )),
    ("PHONE", re.compile(
        r"(?<!\d)"
        r"(?:\+?1[-.\s]?)?"
        r"(?:\(?\d{3}\)?[-.\s]?)"
        r"\d{3}[-.\s]?\d{4}"
        r"(?!\d)"
    )),
    ("IPV4", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    ("DATE_OF_BIRTH", re.compile(
        r"\b(?:DOB|Date of Birth|Birth\s*Date)\s*[:=]?\s*"
        r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
        re.IGNORECASE,
    )),
    ("US_ADDRESS", re.compile(
        r"\b\d{1,6}\s+(?:[A-Za-z]+\s+){0,4}"
        r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|"
        r"Road|Rd|Lane|Ln|Court|Ct|Way|Place|Pl|Circle|Cir)"
        r"\.?\b",
        re.IGNORECASE,
    )),
    ("PERSON_NAME_LABEL", re.compile(
        r"(?:(?:Full\s+)?Name|Contact|Prepared\s+by|Author|Recipient)"
        r"\s*[:=]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    )),
]


def _luhn_check(digits: str) -> bool:
    """Return True if *digits* passes the Luhn algorithm."""
    nums = [int(d) for d in digits if d.isdigit()]
    if len(nums) < 13:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def find_pii(text: str) -> List[RedactionHit]:
    """Return all PII spans found in *text*."""
    hits: List[RedactionHit] = []
    for category, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            matched = m.group(0)

            if category == "CREDIT_CARD":
                digits_only = re.sub(r"\D", "", matched)
                if not _luhn_check(digits_only):
                    continue

            if category == "PERSON_NAME_LABEL" and m.lastindex:
                name = m.group(1)
                offset = m.start(1)
                hits.append(RedactionHit(category, name, offset, offset + len(name)))
                continue

            hits.append(RedactionHit(category, matched, m.start(), m.end()))
    return hits


def redact(text: str, placeholder: str = PLACEHOLDER) -> Tuple[str, List[RedactionHit]]:
    """
    Return a redacted copy of *text* and the list of detected PII spans.

    Replacement is done right-to-left so character offsets stay valid.
    """
    hits = find_pii(text)
    hits.sort(key=lambda h: h.start, reverse=True)

    # Deduplicate overlapping spans (keep the first / longest).
    merged: List[RedactionHit] = []
    occupied_end = len(text) + 1
    for h in hits:
        if h.end <= occupied_end:
            merged.append(h)
            occupied_end = h.start

    redacted = text
    for h in merged:
        redacted = redacted[: h.start] + placeholder + redacted[h.end :]

    merged.reverse()
    return redacted, merged


def redact_rows(rows: List[List[str]], placeholder: str = PLACEHOLDER) -> List[List[str]]:
    """Redact every cell in a list-of-lists (table rows)."""
    out = []
    for row in rows:
        out.append([redact(cell, placeholder)[0] for cell in row])
    return out
