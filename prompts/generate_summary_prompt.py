"""
Generate a ready-to-paste LLM prompt for single-report summarisation.

Usage
-----
    python prompts/generate_summary_prompt.py report.xlsx > ready_to_paste.txt
    python prompts/generate_summary_prompt.py report.pdf --no-redact > ready_to_paste.txt

Then paste the contents into ChatGPT, Copilot Chat, or any other LLM.
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from report_differ.extractors import extract, DocumentContent, TableData
from report_differ.redactor import redact, redact_rows


PROMPT_TEMPLATE = """\
You are a document-summarisation assistant. I will give you the full extracted
content of a business report in structured JSON format. The data has already
been extracted mechanically from the original file and any PII has been
redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference information that is explicitly present in the JSON data I
   provide below. Do NOT use outside knowledge, business definitions, domain
   expertise, or prior training data about any company, product, or industry.

2. Do NOT hallucinate, assume, infer, or speculate about anything not in the
   data. If something is ambiguous or incomplete, state "data not available"
   rather than guess.

3. Do NOT interpret what any figure means for the business. Report WHAT the
   document contains, not WHAT it implies.

4. Produce your output using this exact structure:

   ## Document Overview
   - Filename, format, and metadata (author, title, etc.) if available.
   - Number of text lines, approximate word count, number of tables.

   ## Key Figures
   List every distinct number, currency amount, percentage, and date that
   appears in the text or tables. For each, state:
   - The exact value as it appears in the data.
   - The context it came from (which text line, or which table/row/column).
   Group them by section (Text vs each Table).

   ## Text Content Summary
   Summarise the text content in 3-5 concise bullet points. Each bullet
   must quote or closely paraphrase an actual line from the data — do NOT
   add information that isn't there.

   ## Table Summaries
   For each table:
   - Location / sheet name.
   - Column headers.
   - Row count.
   - For numeric columns: min, max, and total.
   - Reproduce the full table data as a readable markdown table.

   ## Structural Overview
   One short paragraph describing the overall structure of the document
   (e.g. "The document contains 6 paragraphs of text followed by 1 table
   with 3 columns and 2 data rows").

5. Use neutral, factual language only. No subjective adjectives like
   "impressive", "strong", "concerning", "notable", or "significant".

6. Every piece of data you reference MUST appear verbatim in the JSON below.
   If you cannot find it there, do not mention it.

7. **Accuracy is paramount.** Double-check every number you quote against the
   source JSON. If a number does not exist in the JSON, do not include it.

---

**Here is the extracted report data. Summarise it now following the rules above.**

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
        filename=doc.filename,
        format=doc.format,
        text_blocks=new_text,
        tables=new_tables,
        metadata=doc.metadata,
    )


def _doc_to_json(doc: DocumentContent) -> str:
    text_lines = []
    for block in doc.text_blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped:
                text_lines.append(stripped)

    tables = []
    for t in doc.tables:
        tables.append({
            "location": t.sheet_or_page,
            "headers": t.headers,
            "rows": t.rows,
        })

    payload = {
        "filename": doc.filename,
        "format": doc.format,
        "metadata": doc.metadata,
        "text_lines": text_lines,
        "tables": tables,
    }
    return json.dumps(payload, indent=2)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python prompts/generate_summary_prompt.py <report_file> [--no-redact]",
            file=sys.stderr,
        )
        sys.exit(1)

    path = sys.argv[1]
    skip_redact = "--no-redact" in sys.argv

    doc = extract(path)
    if not skip_redact:
        doc = _redact_document(doc)

    report_json = _doc_to_json(doc)
    print(PROMPT_TEMPLATE.format(report_json=report_json))

    text_count = sum(len(block.splitlines()) for block in doc.text_blocks)
    print(
        f"\n--- Generated from: {path} | {text_count} text line(s), "
        f"{len(doc.tables)} table(s) | PII {'skipped' if skip_redact else 'redacted'} ---",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
