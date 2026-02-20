"""
LLM-enhanced metadata, KPI, and metric extraction.

Takes the mechanically extracted, PII-redacted document content and sends it
to an LLM to identify metrics with higher accuracy — catching patterns the
regex engine might miss (e.g. metrics split across lines, implied units,
composite KPIs embedded in prose).

The LLM receives ONLY the extracted data — never the raw file.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from .extractors import DocumentContent
from .metric_extractor import extract_metrics, format_metrics


_SYSTEM_PROMPT = """\
You are a metric-extraction assistant.  You will receive the full extracted
content of a business report — text lines and table data — in structured
JSON format.  The data has already been extracted mechanically and any PII
has been redacted.

STRICT RULES — you MUST follow every one:

1. ONLY reference data that is explicitly present in the JSON input.  Do NOT
   use outside knowledge, business definitions, or domain expertise.

2. Do NOT hallucinate, assume, infer, or speculate.  If a metric's unit or
   context is unclear, label it "unspecified" — do not guess.

3. Your job is to identify every distinct metric, KPI, and measurable data
   point in the document.  A "metric" is any labelled or contextualised
   numeric value — including currencies, percentages, counts, ratios, dates
   tied to periods, and numeric table cells with header context.

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

5. Use neutral, factual language.  No subjective adjectives.

6. Every value you quote MUST appear verbatim in the JSON input.  Double-check
   each number against the source data.

7. Accuracy is paramount.  Missing a metric is better than inventing one.
"""


def _build_user_message(doc: DocumentContent) -> str:
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

    return (
        "Below is the full extracted content of a business report (JSON).  "
        "Extract every metric, KPI, and measurable data point following "
        "your instructions exactly.\n\n"
        "```json\n"
        + json.dumps(payload, indent=2)
        + "\n```"
    )


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def _call_openai(doc: DocumentContent, model: str) -> str:
    try:
        import openai
    except ImportError:
        raise RuntimeError("The 'openai' package is not installed.  pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(doc)},
        ],
    )
    return response.choices[0].message.content


def _call_anthropic(doc: DocumentContent, model: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("The 'anthropic' package is not installed.  pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.1,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(doc)}],
    )
    return response.content[0].text


_PROVIDERS = {
    "openai": {"fn": _call_openai, "default_model": "gpt-4o"},
    "anthropic": {"fn": _call_anthropic, "default_model": "claude-sonnet-4-20250514"},
}


def extract_metrics_with_llm(
    doc: DocumentContent,
    provider: str,
    model: Optional[str] = None,
) -> str:
    info = _PROVIDERS.get(provider)
    if info is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'.  "
            f"Supported: {', '.join(_PROVIDERS)}"
        )

    chosen_model = model or info["default_model"]
    call_fn = info["fn"]

    try:
        result = call_fn(doc, chosen_model)
        header = (
            f"[LLM-enhanced metric extraction via {provider} / {chosen_model}]\n"
            + "=" * 64 + "\n\n"
        )
        return header + result

    except Exception as exc:
        print(
            f"[warn] LLM metric extraction failed ({exc}); "
            f"falling back to mechanical extraction.",
            file=sys.stderr,
        )
        mech = extract_metrics(doc)
        return format_metrics(mech, fmt="plain")
