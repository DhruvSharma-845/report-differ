"""
Phase 2 — LLM-enhanced diff analysis.

Takes the mechanically computed, PII-redacted list of `Difference` records and
sends them to an LLM for a more polished, categorised summary.

Design constraints
------------------
* The LLM receives **only** the structured diff data — never the raw documents.
* The system prompt explicitly forbids the model from using outside knowledge,
  making assumptions, or inventing facts not present in the diff.
* If the LLM call fails for any reason, the tool falls back to the standard
  mechanical summary automatically.

Supported providers
-------------------
* **OpenAI**    — requires ``OPENAI_API_KEY`` env var.  Default model: ``gpt-4o``.
* **Anthropic** — requires ``ANTHROPIC_API_KEY`` env var.  Default model: ``claude-sonnet-4-20250514``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Optional

from .differ import ChangeType, Difference
from .summariser import summarise as mechanical_summarise


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a document-comparison assistant.  You will receive a structured list of
factual differences between two versions of the same business report.

STRICT RULES — you MUST follow every one:

1. ONLY reference facts explicitly present in the diff data provided.  Do NOT
   use any outside knowledge, business definitions, or domain expertise.
2. Do NOT hallucinate, assume, infer, or speculate about anything not in the
   data.  If something is unclear, say "insufficient data" rather than guess.
3. Do NOT interpret what a change means for the business.  Report WHAT changed,
   not WHY or what it implies.
4. For numeric changes, compute the absolute difference and the percentage
   change relative to the old value.  Show both.
5. Categorise each change as one of: NUMERIC, TEXTUAL, STRUCTURAL (row/column
   added or removed), or HEADER.
6. Assess the magnitude of each change as HIGH (>20% or large structural
   change), MEDIUM (5-20%), or LOW (<5% or minor text edit).  Base this purely
   on the numbers — not on business importance.
7. Produce your output in the following structure:

   ## Executive Overview
   One short paragraph summarising the total number and nature of changes.

   ## Detailed Changes
   Group changes by their source section (e.g. "Text", "Table [Revenue]").
   For each change list:
   - Category (NUMERIC / TEXTUAL / STRUCTURAL / HEADER)
   - Location
   - Old value → New value
   - Absolute and percentage delta (for numeric changes)
   - Magnitude tag (HIGH / MEDIUM / LOW)

   ## Statistics
   - Total changes
   - Breakdown by category
   - Breakdown by magnitude

8. Use neutral, factual language throughout.  No adjectives like "significant",
   "concerning", "impressive", or "notable" — use the magnitude tag instead.
9. All data you reference MUST appear verbatim in the diff input.  If you
   cannot find it there, do not mention it.
"""


def _build_user_message(diffs: List[Difference]) -> str:
    records = []
    for d in diffs:
        records.append({
            "section": d.section,
            "change_type": d.change_type.value,
            "location": d.location,
            "old_value": d.old_value,
            "new_value": d.new_value,
        })

    return (
        "Below is the structured diff data (JSON).  Analyse it following "
        "your instructions exactly.\n\n"
        "```json\n"
        + json.dumps(records, indent=2)
        + "\n```"
    )


# ---------------------------------------------------------------------------
# Provider: OpenAI
# ---------------------------------------------------------------------------

def _call_openai(diffs: List[Difference], model: str) -> str:
    try:
        import openai
    except ImportError:
        raise RuntimeError(
            "The 'openai' package is not installed.  "
            "Install it with:  pip install openai"
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set.  "
            "Export it before using --llm openai."
        )

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(diffs)},
        ],
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Provider: Anthropic
# ---------------------------------------------------------------------------

def _call_anthropic(diffs: List[Difference], model: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is not installed.  "
            "Install it with:  pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set.  "
            "Export it before using --llm anthropic."
        )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.1,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _build_user_message(diffs)},
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


def analyse_with_llm(
    diffs: List[Difference],
    provider: str,
    model: Optional[str] = None,
) -> str:
    """
    Send the mechanical diff to an LLM for enhanced analysis.

    Parameters
    ----------
    diffs : list[Difference]
        Already-computed, PII-redacted differences.
    provider : str
        ``"openai"`` or ``"anthropic"``.
    model : str | None
        Model name override.  Uses the provider's default if *None*.

    Returns
    -------
    str
        The LLM-generated analysis.  Falls back to the mechanical summary
        if the LLM call fails for any reason.
    """
    if not diffs:
        return "No factual differences detected between the two document versions."

    info = _PROVIDERS.get(provider)
    if info is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'.  "
            f"Supported: {', '.join(_PROVIDERS)}"
        )

    chosen_model = model or info["default_model"]
    call_fn = info["fn"]

    try:
        result = call_fn(diffs, chosen_model)
        header = (
            f"[LLM-enhanced analysis via {provider} / {chosen_model}]\n"
            f"[Ground truth: {len(diffs)} mechanical diff(s) — see --format plain for raw data]\n"
            + "=" * 64 + "\n\n"
        )
        return header + result

    except Exception as exc:
        print(
            f"[warn] LLM analysis failed ({exc}); falling back to mechanical summary.",
            file=sys.stderr,
        )
        return mechanical_summarise(diffs, fmt="plain")
