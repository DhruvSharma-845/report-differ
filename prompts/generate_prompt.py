"""
Generate a ready-to-paste LLM prompt with the diff data embedded.

Usage
-----
    python prompts/generate_prompt.py old_report.xlsx new_report.xlsx > ready_to_paste.txt

Then paste the contents of ready_to_paste.txt into ChatGPT, Copilot Chat, or
any other LLM interface.  No API keys needed.
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from report_differ.extractors import extract, DocumentContent, TableData
from report_differ.redactor import redact, redact_rows
from report_differ.differ import compare


PROMPT_TEMPLATE = """\
You are a document-comparison assistant. I will give you a structured JSON list
of factual differences between two versions of the same business report. The
data has already been extracted mechanically and any PII has been redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference facts that are explicitly present in the JSON diff data I
   provide below. Do NOT use any outside knowledge, business definitions, or
   domain expertise.

2. Do NOT hallucinate, assume, infer, or speculate about anything that is not
   in the data. If something is unclear, state "insufficient data" — do not
   guess.

3. Do NOT interpret what any change means for the business. Report WHAT changed,
   not WHY it changed or what it implies.

4. For any change where both old_value and new_value are numeric, compute:
   - The absolute difference (new − old).
   - The percentage change relative to the old value: ((new − old) / old) × 100.
   Show both numbers.

5. Categorise each change as exactly one of:
   - **NUMERIC** — both old and new values are numbers.
   - **TEXTUAL** — one or both values are non-numeric text.
   - **STRUCTURAL** — a row, column, or entire table was added or removed.
   - **HEADER** — the table header row itself changed.

6. Assess the magnitude of each change:
   - **HIGH** — numeric change >20%, or a large structural change (entire
     table / multiple rows added or removed).
   - **MEDIUM** — numeric change between 5% and 20%.
   - **LOW** — numeric change <5%, or a minor text edit.

7. Produce your output using this exact structure:

   ## Executive Overview
   One short paragraph: how many total changes, and a neutral one-sentence
   characterisation of the mix (e.g. "5 changes detected: 3 numeric, 1
   textual, 1 structural").

   ## Detailed Changes
   Group by the "section" field from the JSON (e.g. "Text", "Table [Revenue]").
   For each change, show:
   - Category tag
   - Location
   - Old value → New value
   - Absolute delta and percentage delta (numeric changes only)
   - Magnitude tag

   ## Statistics
   A summary table:
   - Total changes
   - Count by category (NUMERIC / TEXTUAL / STRUCTURAL / HEADER)
   - Count by magnitude (HIGH / MEDIUM / LOW)

8. Use neutral, factual language only. Do NOT use subjective adjectives such as
   "significant", "concerning", "impressive", "notable", "alarming", etc. Use
   the magnitude tag (HIGH / MEDIUM / LOW) instead.

9. Every piece of data you reference MUST appear verbatim in the JSON below.
   If you cannot find it there, do not mention it.

---

**Here is the diff data. Analyse it now following the rules above.**

```json
{diff_json}
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
        filename=doc.filename,
        format=doc.format,
        text_blocks=new_text,
        tables=new_tables,
        metadata=doc.metadata,
    )


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python prompts/generate_prompt.py <old_file> <new_file> "
            "[--no-redact]",
            file=sys.stderr,
        )
        sys.exit(1)

    old_path = sys.argv[1]
    new_path = sys.argv[2]
    skip_redact = "--no-redact" in sys.argv

    old_doc = extract(old_path)
    new_doc = extract(new_path)

    if not skip_redact:
        old_doc = _redact_document(old_doc)
        new_doc = _redact_document(new_doc)

    diffs = compare(old_doc, new_doc)

    records = []
    for d in diffs:
        records.append({
            "section": d.section,
            "change_type": d.change_type.value,
            "location": d.location,
            "old_value": d.old_value,
            "new_value": d.new_value,
        })

    diff_json = json.dumps(records, indent=2)
    print(PROMPT_TEMPLATE.format(diff_json=diff_json))

    print(
        f"\n--- Generated from: {old_path} vs {new_path} "
        f"| {len(diffs)} diff(s) | PII {'skipped' if skip_redact else 'redacted'} ---",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
