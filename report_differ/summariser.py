"""
Summary generator.

Produces a concise, neutral, factual summary from a list of `Difference`
records.  The language is deliberately mechanical — no business
interpretation, no inferred meaning.
"""

from __future__ import annotations

import json
import textwrap
from typing import List

from .differ import ChangeType, Difference


def _cap(text: str | None, limit: int = 120) -> str:
    if not text:
        return "(empty)"
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def summarise_plain(diffs: List[Difference]) -> str:
    if not diffs:
        return "No factual differences detected between the two document versions."

    sections: dict[str, List[str]] = {}
    for d in diffs:
        bucket = sections.setdefault(d.section, [])
        if d.change_type == ChangeType.ADDED:
            bucket.append(f"  + ADDED at {d.location}: {_cap(d.new_value)}")
        elif d.change_type == ChangeType.REMOVED:
            bucket.append(f"  - REMOVED at {d.location}: {_cap(d.old_value)}")
        else:
            bucket.append(
                f"  ~ CHANGED at {d.location}:\n"
                f"      was: {_cap(d.old_value)}\n"
                f"      now: {_cap(d.new_value)}"
            )

    lines = [
        f"Difference Summary  ({len(diffs)} change(s) detected)",
        "=" * 56,
    ]
    for section, items in sections.items():
        lines.append(f"\n[{section}]")
        lines.extend(items)

    return "\n".join(lines)


def summarise_json(diffs: List[Difference]) -> str:
    records = []
    for d in diffs:
        records.append({
            "section": d.section,
            "change_type": d.change_type.value,
            "location": d.location,
            "old_value": d.old_value,
            "new_value": d.new_value,
        })
    return json.dumps({"total_changes": len(records), "differences": records}, indent=2)


def summarise(diffs: List[Difference], fmt: str = "plain") -> str:
    if fmt == "json":
        return summarise_json(diffs)
    return summarise_plain(diffs)
