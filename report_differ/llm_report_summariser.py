"""
LLM-enhanced single-report summariser.

Takes the mechanically extracted, PII-redacted document content and sends it
to an LLM for a polished, structured summary with higher accuracy.

The LLM receives ONLY the extracted data — never the raw file.  The system
prompt constrains the model to report only what is visible in the data.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from .extractors import DocumentContent, TableData
from .report_summariser import summarise_report as mechanical_summarise


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a document-summarisation assistant.  You will receive the full
extracted content of a single business report — text lines and table data —
in structured JSON format.  The data has already been extracted mechanically
and any PII has been redacted.

STRICT RULES — you MUST follow every one:

1. ONLY reference information that is explicitly present in the extracted data
   provided.  Do NOT use outside knowledge, business definitions, domain
   expertise, or prior training data about any company, product, or industry.

2. Do NOT hallucinate, assume, infer, or speculate about anything not in the
   data.  If something is ambiguous or incomplete, say "data not available"
   rather than guess.

3. Do NOT interpret what any figure means for the business.  Report WHAT the
   document contains, not WHAT it implies.

4. Produce your output using this exact structure:

   ## Document Overview
   - Filename, format, and metadata (author, title, etc.) if available.
   - Number of text lines, approximate word count, number of tables.

   ## Key Figures
   List every distinct number, currency amount, percentage, and date that
   appears in the text or tables.  For each, state:
   - The exact value as it appears in the data.
   - The context (which line or which table/row/column it came from).
   Group them by section (Text vs each Table).

   ## Text Content Summary
   Summarise the text content in 3-5 concise bullet points.  Each bullet
   must quote or closely paraphrase an actual line from the data — do NOT
   add information that isn't there.

   ## Table Summaries
   For each table:
   - Location / sheet name.
   - Column headers.
   - Row count.
   - For numeric columns: min, max, and total.
   - Reproduce the table data in a readable markdown table.

   ## Structural Overview
   One short paragraph describing the overall structure of the document
   (e.g. "The document contains 6 paragraphs of text followed by 1 table
   with 3 columns and 2 data rows").

5. Use neutral, factual language only.  No subjective adjectives like
   "impressive", "strong", "concerning".

6. Every piece of data you reference MUST appear verbatim in the JSON input.
   If you cannot find it there, do not mention it.

7. Accuracy is paramount.  Double-check every number you quote against the
   source JSON.  If a number does not appear in the JSON, do not include it.
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
        "Summarise it following your instructions exactly.\n\n"
        "```json\n"
        + json.dumps(payload, indent=2)
        + "\n```"
    )


# ---------------------------------------------------------------------------
# Provider: OpenAI
# ---------------------------------------------------------------------------

def _call_openai(doc: DocumentContent, model: str) -> str:
    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is not installed.  "
            "Install it with:  pip install openai"
        )

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


# ---------------------------------------------------------------------------
# Provider: Anthropic
# ---------------------------------------------------------------------------

def _call_anthropic(doc: DocumentContent, model: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed.  "
            "Install it with:  pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.1,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _build_user_message(doc)},
        ],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "openai": {"fn": _call_openai, "default_model": "gpt-4o"},
    "anthropic": {"fn": _call_anthropic, "default_model": "claude-sonnet-4-20250514"},
}


def summarise_report_with_llm(
    doc: DocumentContent,
    provider: str,
    model: Optional[str] = None,
) -> str:
    """
    Send extracted document content to an LLM for a structured summary.

    Falls back to the mechanical summary if the LLM call fails.
    """
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
            f"[LLM-enhanced report summary via {provider} / {chosen_model}]\n"
            + "=" * 64 + "\n\n"
        )
        return header + result

    except Exception as exc:
        print(
            f"[warn] LLM summarisation failed ({exc}); falling back to mechanical summary.",
            file=sys.stderr,
        )
        return mechanical_summarise(doc, fmt="plain")
