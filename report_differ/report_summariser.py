"""
Single-report summariser (code-based, no LLM).

Accepts a `DocumentContent` object and produces a factual, extractive summary
of what the document contains.  The summary is purely mechanical:

* Document metadata and structure (format, page/sheet count, text lines, tables).
* Key factual lines — lines containing numbers, currency, dates, or percentages
  are treated as high-information-density content and surfaced verbatim.
* Table profiles — for each table: location, column headers, row count, and
  numeric column statistics (min, max, sum) when applicable.

No interpretation, no business logic, no inference.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import List, Optional

from .extractors import DocumentContent, TableData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"(?:\$|€|£)?\s*[\d,]+\.?\d*\s*%?"
    r"|[\d,]+\.?\d*\s*(?:million|billion|thousand|mn|bn|k)\b",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
    r"|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"[\s,]+\d{1,2}[\s,]+\d{2,4})"
    r"|(?:Q[1-4]\s*\d{4})"
    r"|(?:FY\s*\d{2,4})",
    re.IGNORECASE,
)


def _is_factual_line(line: str) -> bool:
    """Return True if the line contains numbers, currency, dates, or percentages."""
    if _NUMBER_RE.search(line):
        return True
    if _DATE_RE.search(line):
        return True
    if "%" in line:
        return True
    return False


def _try_float(val: str) -> Optional[float]:
    cleaned = val.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
    cleaned = cleaned.rstrip("%")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


@dataclass
class ColumnProfile:
    name: str
    numeric_count: int = 0
    text_count: int = 0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    total: float = 0.0


@dataclass
class TableProfile:
    location: str
    headers: List[str]
    row_count: int
    columns: List[ColumnProfile] = field(default_factory=list)


def _profile_table(table: TableData) -> TableProfile:
    cols: List[ColumnProfile] = []
    for i, header in enumerate(table.headers):
        cp = ColumnProfile(name=header)
        for row in table.rows:
            if i >= len(row):
                continue
            val = row[i]
            num = _try_float(val)
            if num is not None:
                cp.numeric_count += 1
                cp.total += num
                if cp.min_val is None or num < cp.min_val:
                    cp.min_val = num
                if cp.max_val is None or num > cp.max_val:
                    cp.max_val = num
            elif val.strip():
                cp.text_count += 1
        cols.append(cp)

    return TableProfile(
        location=table.location if hasattr(table, "location") else table.sheet_or_page,
        headers=table.headers,
        row_count=len(table.rows),
        columns=cols,
    )


# ---------------------------------------------------------------------------
# Plain-text summary
# ---------------------------------------------------------------------------

def summarise_report_plain(doc: DocumentContent) -> str:
    lines: List[str] = []

    lines.append(f"Report Summary: {doc.filename}")
    lines.append("=" * 56)

    lines.append(f"\nFormat : {doc.format.upper()}")
    if doc.metadata:
        for k, v in doc.metadata.items():
            if v:
                lines.append(f"  {k}: {v}")

    all_text = "\n".join(doc.text_blocks)
    text_lines = [l for l in all_text.splitlines() if l.strip()]
    word_count = sum(len(l.split()) for l in text_lines)

    lines.append(f"\nText   : {len(text_lines)} line(s), ~{word_count} word(s)")
    lines.append(f"Tables : {len(doc.tables)}")

    factual = [l for l in text_lines if _is_factual_line(l)]
    if factual:
        lines.append(f"\n--- Key factual lines ({len(factual)}) ---")
        for fl in factual:
            lines.append(f"  > {fl.strip()}")

    non_factual = [l for l in text_lines if not _is_factual_line(l)]
    if non_factual:
        lines.append(f"\n--- Other text lines ({len(non_factual)}) ---")
        for nfl in non_factual:
            lines.append(f"    {nfl.strip()}")

    if doc.tables:
        lines.append("\n--- Table profiles ---")
        for table in doc.tables:
            tp = _profile_table(table)
            lines.append(f"\n  [{tp.location}]  {tp.row_count} data row(s)")
            lines.append(f"  Headers: {' | '.join(tp.headers)}")
            for cp in tp.columns:
                if cp.numeric_count > 0:
                    lines.append(
                        f"    {cp.name}: {cp.numeric_count} numeric value(s)"
                        f"  min={cp.min_val}  max={cp.max_val}  sum={cp.total}"
                    )
                elif cp.text_count > 0:
                    lines.append(f"    {cp.name}: {cp.text_count} text value(s)")

            if tp.row_count <= 20:
                lines.append(f"  Data rows:")
                for ri, row in enumerate(table.rows, start=2):
                    lines.append(f"    Row {ri}: {' | '.join(row)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON summary
# ---------------------------------------------------------------------------

def summarise_report_json(doc: DocumentContent) -> str:
    all_text = "\n".join(doc.text_blocks)
    text_lines = [l for l in all_text.splitlines() if l.strip()]
    factual = [l.strip() for l in text_lines if _is_factual_line(l)]
    non_factual = [l.strip() for l in text_lines if not _is_factual_line(l)]

    table_profiles = []
    for table in doc.tables:
        tp = _profile_table(table)
        col_info = []
        for cp in tp.columns:
            entry = {"name": cp.name, "numeric_count": cp.numeric_count, "text_count": cp.text_count}
            if cp.numeric_count > 0:
                entry.update({"min": cp.min_val, "max": cp.max_val, "sum": cp.total})
            col_info.append(entry)

        t_entry = {
            "location": tp.location,
            "headers": tp.headers,
            "row_count": tp.row_count,
            "columns": col_info,
        }
        if tp.row_count <= 20:
            t_entry["rows"] = table.rows
        table_profiles.append(t_entry)

    result = {
        "filename": doc.filename,
        "format": doc.format,
        "metadata": doc.metadata,
        "text": {
            "total_lines": len(text_lines),
            "word_count": sum(len(l.split()) for l in text_lines),
            "key_factual_lines": factual,
            "other_lines": non_factual,
        },
        "tables": table_profiles,
    }

    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarise_report(doc: DocumentContent, fmt: str = "plain") -> str:
    """Produce a factual summary of a single document."""
    if fmt == "json":
        return summarise_report_json(doc)
    return summarise_report_plain(doc)
