"""
Metadata, KPI, and metric extraction engine (code-based, no LLM).

Scans the extracted `DocumentContent` and identifies three categories of
structured information:

1. **Document metadata** — file properties, structure stats, dates found.
2. **Inline metrics** — labelled numeric values found in text lines
   (e.g. "Revenue: $1.2M", "Growth: 14%", "Headcount = 340").
3. **Tabular metrics** — numeric cells in tables, enriched with their
   column header and row label for context.

Detection is pattern-based.  The engine does not know what "Revenue" means —
it recognises the *shape* of a metric (label + number) and extracts both
the label and the value verbatim.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .extractors import DocumentContent, TableData


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DocumentMeta:
    filename: str
    format: str
    file_metadata: dict
    text_line_count: int
    word_count: int
    table_count: int
    dates_found: List[str]
    slide_or_page_count: int


@dataclass
class InlineMetric:
    """A labelled numeric value found in running text."""
    label: str
    raw_value: str
    numeric_value: Optional[float]
    unit: str
    source_line: str
    line_number: int


@dataclass
class TabularMetric:
    """A numeric cell in a table, with row/column context."""
    table_location: str
    column_header: str
    row_label: str
    raw_value: str
    numeric_value: Optional[float]
    row_index: int
    col_index: int


@dataclass
class ExtractionResult:
    metadata: DocumentMeta
    inline_metrics: List[InlineMetric] = field(default_factory=list)
    tabular_metrics: List[TabularMetric] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = r"[\$€£¥₹]"

# Labelled metric: "Some Label: $1,234.56" or "Some Label = 14.5%"
_LABELLED_METRIC_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 /&\-]{1,60}?)"
    r"\s*[:=–—\-]\s*"
    r"(?P<value>"
    r"(?:" + _CURRENCY_SYMBOLS + r"\s*)?"
    r"-?[\d,]+\.?\d*"
    r"(?:\s*(?:million|billion|thousand|mn|bn|k|M|B|K)(?![a-z]))?"
    r"\s*%?"
    r")",
    re.IGNORECASE,
)

# Standalone currency: "$1,234.56" without a preceding label
_CURRENCY_RE = re.compile(
    r"(?P<value>" + _CURRENCY_SYMBOLS + r"\s*-?[\d,]+\.?\d*"
    r"(?:\s*(?:million|billion|thousand|mn|bn|k|M|B|K)(?![a-z]))?)",
    re.IGNORECASE,
)

# Standalone percentage: "14.5%"
_PERCENTAGE_RE = re.compile(
    r"(?P<value>-?[\d,]+\.?\d*\s*%)"
)

# Ratio pattern: "12:1" or "3.5:1"
_RATIO_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 /&\-]{1,40}?)"
    r"\s*[:=–—\-]\s*"
    r"(?P<value>\d+\.?\d*\s*:\s*\d+\.?\d*)"
)

# Dates (broad)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"
    r"|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"[\s,]+\d{1,2}[\s,]*\d{2,4})"
    r"|(?:Q[1-4]\s*['']?\d{2,4})"
    r"|(?:FY\s*['']?\d{2,4})"
    r"|(?:20\d{2}|19\d{2})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MULTIPLIERS = {
    "k": 1_000, "K": 1_000, "thousand": 1_000,
    "m": 1_000_000, "M": 1_000_000, "million": 1_000_000, "mn": 1_000_000,
    "b": 1_000_000_000, "B": 1_000_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000,
}


def _parse_numeric(raw: str) -> Optional[float]:
    s = raw.strip().rstrip("%")
    for sym in "$€£¥₹":
        s = s.replace(sym, "")
    s = s.replace(",", "").strip()

    multiplier = 1.0
    for suffix, mult in _MULTIPLIERS.items():
        if s.lower().endswith(suffix.lower()):
            s = s[: -len(suffix)].strip()
            multiplier = mult
            break

    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return None


def _detect_unit(raw: str) -> str:
    raw = raw.strip()
    if "%" in raw:
        return "percent"
    for sym, name in [("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"), ("₹", "INR")]:
        if sym in raw:
            return name
    if ":" in raw and re.match(r"\d+\.?\d*\s*:\s*\d+\.?\d*", raw):
        return "ratio"
    return "number"


def _try_float_cell(val: str) -> Optional[float]:
    cleaned = val.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()
    cleaned = cleaned.rstrip("%")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

def _extract_metadata(doc: DocumentContent) -> DocumentMeta:
    all_text = "\n".join(doc.text_blocks)
    text_lines = [l for l in all_text.splitlines() if l.strip()]
    word_count = sum(len(l.split()) for l in text_lines)

    dates: List[str] = []
    seen = set()
    for m in _DATE_RE.finditer(all_text):
        d = m.group(0).strip()
        if d not in seen:
            dates.append(d)
            seen.add(d)

    slide_or_page = len(doc.text_blocks)

    return DocumentMeta(
        filename=doc.filename,
        format=doc.format,
        file_metadata=doc.metadata,
        text_line_count=len(text_lines),
        word_count=word_count,
        table_count=len(doc.tables),
        dates_found=dates,
        slide_or_page_count=slide_or_page,
    )


def _extract_inline_metrics(doc: DocumentContent) -> List[InlineMetric]:
    metrics: List[InlineMetric] = []
    seen_spans: set = set()
    line_num = 0

    for block in doc.text_blocks:
        for line in block.splitlines():
            line_num += 1
            stripped = line.strip()
            if not stripped:
                continue

            for m in _LABELLED_METRIC_RE.finditer(stripped):
                label = m.group("label").strip()
                raw_val = m.group("value").strip()
                span_key = (line_num, m.start(), m.end())
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)

                metrics.append(InlineMetric(
                    label=label,
                    raw_value=raw_val,
                    numeric_value=_parse_numeric(raw_val),
                    unit=_detect_unit(raw_val),
                    source_line=stripped,
                    line_number=line_num,
                ))

            for m in _RATIO_RE.finditer(stripped):
                span_key = (line_num, m.start(), m.end())
                if span_key in seen_spans:
                    continue
                seen_spans.add(span_key)
                metrics.append(InlineMetric(
                    label=m.group("label").strip(),
                    raw_value=m.group("value").strip(),
                    numeric_value=None,
                    unit="ratio",
                    source_line=stripped,
                    line_number=line_num,
                ))

    return metrics


def _extract_tabular_metrics(doc: DocumentContent) -> List[TabularMetric]:
    metrics: List[TabularMetric] = []

    for table in doc.tables:
        first_col_is_label = True
        if table.headers and table.rows:
            num_first = sum(
                1 for r in table.rows
                if r and _try_float_cell(r[0]) is not None
            )
            if num_first > len(table.rows) * 0.5:
                first_col_is_label = False

        for ri, row in enumerate(table.rows):
            row_label = row[0] if row and first_col_is_label else f"Row {ri + 2}"

            for ci, cell_val in enumerate(row):
                if first_col_is_label and ci == 0:
                    continue
                num = _try_float_cell(cell_val)
                if num is None:
                    continue

                col_header = (
                    table.headers[ci]
                    if ci < len(table.headers)
                    else f"Col {ci + 1}"
                )

                metrics.append(TabularMetric(
                    table_location=table.sheet_or_page,
                    column_header=col_header,
                    row_label=row_label,
                    raw_value=cell_val.strip(),
                    numeric_value=num,
                    row_index=ri + 2,
                    col_index=ci + 1,
                ))

    return metrics


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_metrics(doc: DocumentContent) -> ExtractionResult:
    """Extract metadata, inline metrics, and tabular metrics from a document."""
    return ExtractionResult(
        metadata=_extract_metadata(doc),
        inline_metrics=_extract_inline_metrics(doc),
        tabular_metrics=_extract_tabular_metrics(doc),
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_plain(result: ExtractionResult) -> str:
    lines: List[str] = []
    m = result.metadata

    lines.append(f"Metric Extraction: {m.filename}")
    lines.append("=" * 60)

    lines.append(f"\n── Document Metadata ──")
    lines.append(f"  Format         : {m.format.upper()}")
    lines.append(f"  Pages/Slides   : {m.slide_or_page_count}")
    lines.append(f"  Text lines     : {m.text_line_count}")
    lines.append(f"  Word count     : ~{m.word_count}")
    lines.append(f"  Tables         : {m.table_count}")
    if m.file_metadata:
        for k, v in m.file_metadata.items():
            if v:
                lines.append(f"  {k}: {v}")
    if m.dates_found:
        lines.append(f"  Dates found    : {', '.join(m.dates_found)}")

    if result.inline_metrics:
        lines.append(f"\n── Inline Metrics ({len(result.inline_metrics)}) ──")
        for im in result.inline_metrics:
            nv = f" (= {im.numeric_value:,.2f})" if im.numeric_value is not None else ""
            lines.append(f"  {im.label}: {im.raw_value}  [{im.unit}]{nv}")
            lines.append(f"      source: \"{im.source_line}\"  (line {im.line_number})")

    if result.tabular_metrics:
        by_table: dict[str, List[TabularMetric]] = {}
        for tm in result.tabular_metrics:
            by_table.setdefault(tm.table_location, []).append(tm)

        lines.append(f"\n── Tabular Metrics ({len(result.tabular_metrics)}) ──")
        for table_loc, tms in by_table.items():
            lines.append(f"\n  [{table_loc}]")
            for tm in tms:
                nv = f"{tm.numeric_value:,.2f}" if tm.numeric_value is not None else tm.raw_value
                lines.append(
                    f"    {tm.row_label} / {tm.column_header}: "
                    f"{tm.raw_value}  (= {nv})"
                )

    total = len(result.inline_metrics) + len(result.tabular_metrics)
    lines.append(f"\n── Summary ──")
    lines.append(f"  Total metrics found : {total}")
    lines.append(f"  Inline (text)       : {len(result.inline_metrics)}")
    lines.append(f"  Tabular (tables)    : {len(result.tabular_metrics)}")

    return "\n".join(lines)


def format_json(result: ExtractionResult) -> str:
    m = result.metadata
    out = {
        "metadata": {
            "filename": m.filename,
            "format": m.format,
            "file_metadata": m.file_metadata,
            "text_line_count": m.text_line_count,
            "word_count": m.word_count,
            "table_count": m.table_count,
            "pages_or_slides": m.slide_or_page_count,
            "dates_found": m.dates_found,
        },
        "inline_metrics": [
            {
                "label": im.label,
                "raw_value": im.raw_value,
                "numeric_value": im.numeric_value,
                "unit": im.unit,
                "source_line": im.source_line,
                "line_number": im.line_number,
            }
            for im in result.inline_metrics
        ],
        "tabular_metrics": [
            {
                "table_location": tm.table_location,
                "column_header": tm.column_header,
                "row_label": tm.row_label,
                "raw_value": tm.raw_value,
                "numeric_value": tm.numeric_value,
                "row_index": tm.row_index,
                "col_index": tm.col_index,
            }
            for tm in result.tabular_metrics
        ],
        "summary": {
            "total_metrics": len(result.inline_metrics) + len(result.tabular_metrics),
            "inline_count": len(result.inline_metrics),
            "tabular_count": len(result.tabular_metrics),
        },
    }
    return json.dumps(out, indent=2)


def format_metrics(result: ExtractionResult, fmt: str = "plain") -> str:
    if fmt == "json":
        return format_json(result)
    return format_plain(result)
