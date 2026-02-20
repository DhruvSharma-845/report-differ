"""
Generate a ready-to-paste LLM prompt for metric / KPI extraction.

Usage
-----
    python prompts/generate_metrics_prompt.py report.xlsx > ready_to_paste.txt
    python prompts/generate_metrics_prompt.py deck.pptx --no-redact > ready_to_paste.txt
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from report_differ.extractors import extract, DocumentContent, TableData
from report_differ.redactor import redact, redact_rows


PROMPT_TEMPLATE = """\
You are a metric-extraction assistant. I will give you the full extracted
content of a business report in structured JSON format. The data has already
been extracted mechanically and any PII has been redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference data that is explicitly present in the JSON I provide below.
   Do NOT use outside knowledge, business definitions, or domain expertise.

2. Do NOT hallucinate, assume, infer, or speculate. If a metric's unit or
   context is unclear, label it "unspecified" — do not guess.

3. Your job is to identify every distinct metric, KPI, and measurable data
   point in the document. A "metric" is any labelled or contextualised numeric
   value — including currencies, percentages, counts, ratios, dates tied to
   periods, and numeric table cells with header context.

4. Produce your output using this exact structure:

   ## Document Metadata
   - Filename, format, pages/slides, text lines, word count, tables.
   - All dates and time periods found.
   - Any file-level metadata (author, title, etc.).

   ## Inline Metrics (from text)
   For each metric found in text lines, list:
   - **Label** — the text label or context preceding the number.
   - **Value** — the exact numeric value as it appears.
   - **Parsed value** — the number in standard form (e.g. "$1.2M" → 1,200,000).
   - **Unit** — currency code, "percent", "ratio", "count", or "unspecified".
   - **Source** — the exact line it was extracted from.

   ## Tabular Metrics (from tables)
   For each table, reproduce it as a markdown table and then list every numeric
   cell as a metric:
   - **Row label** (first column or row index) + **Column header** → **Value**.

   ## KPI Summary Table
   A consolidated markdown table of ALL metrics (inline + tabular) with columns:
   | # | Label | Value | Unit | Source (text line / table location) |

   ## Statistics
   - Total metrics found.
   - Breakdown: inline vs tabular.
   - Breakdown by unit type (currency, percent, ratio, count, unspecified).

5. Use neutral, factual language. No subjective adjectives.

6. Every value you quote MUST appear verbatim in the JSON input. Double-check
   each number against the source data.

7. **Accuracy is paramount.** Missing a metric is better than inventing one.

---

**Here is the extracted report data. Extract all metrics now following the rules above.**

```json
{report_json}
```
"""


def _redact_document(doc: DocumentContent) -> DocumentContent:
    new_text = [redact(block)[0] for block in doc.text_blocks]
    new_tables = []
    for tbl in doc.tables:
        new_tables.append(TableData(
            sheet_or_page=tbl.sheet_or_page,
            headers=[redact(h)[0] for h in tbl.headers],
            rows=redact_rows(tbl.rows),
        ))
    return DocumentContent(
        filename=doc.filename, format=doc.format,
        text_blocks=new_text, tables=new_tables, metadata=doc.metadata,
    )


def _doc_to_json(doc: DocumentContent) -> str:
    text_lines = []
    for block in doc.text_blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped:
                text_lines.append(stripped)
    tables = [{"location": t.sheet_or_page, "headers": t.headers, "rows": t.rows} for t in doc.tables]
    return json.dumps({
        "filename": doc.filename, "format": doc.format,
        "metadata": doc.metadata, "text_lines": text_lines, "tables": tables,
    }, indent=2)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python prompts/generate_metrics_prompt.py <report> [--no-redact]", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    skip_redact = "--no-redact" in sys.argv

    doc = extract(path)
    if not skip_redact:
        doc = _redact_document(doc)

    print(PROMPT_TEMPLATE.format(report_json=_doc_to_json(doc)))
    print(f"\n--- Generated from: {path} | PII {'skipped' if skip_redact else 'redacted'} ---", file=sys.stderr)


if __name__ == "__main__":
    main()
