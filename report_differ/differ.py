"""
Structural diff engine.

Compares two `DocumentContent` objects and produces a list of `Difference`
records.  The comparison is purely mechanical:

* **Text blocks** — difflib SequenceMatcher over lines, reporting insertions,
  deletions, and replacements.
* **Tables** — matched by (sheet/page label + header signature).  Once matched,
  cells are compared row-by-row and column-by-column.

No business-level interpretation is applied.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .extractors import DocumentContent, TableData


class ChangeType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class Difference:
    section: str
    change_type: ChangeType
    location: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    detail: str = ""


# ---------------------------------------------------------------------------
# Text comparison
# ---------------------------------------------------------------------------

def _diff_text_blocks(
    old_blocks: List[str],
    new_blocks: List[str],
) -> List[Difference]:
    old_lines = "\n".join(old_blocks).splitlines()
    new_lines = "\n".join(new_blocks).splitlines()

    diffs: List[Difference] = []
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue

        old_snippet = "\n".join(old_lines[i1:i2]) if i1 < i2 else None
        new_snippet = "\n".join(new_lines[j1:j2]) if j1 < j2 else None

        if tag == "replace":
            ct = ChangeType.MODIFIED
        elif tag == "insert":
            ct = ChangeType.ADDED
        else:
            ct = ChangeType.REMOVED

        diffs.append(Difference(
            section="Text",
            change_type=ct,
            location=f"Lines {i1 + 1}-{i2}" if old_snippet else f"After line {i1}",
            old_value=old_snippet,
            new_value=new_snippet,
        ))

    return diffs


# ---------------------------------------------------------------------------
# Table comparison
# ---------------------------------------------------------------------------

def _table_signature(t: TableData) -> str:
    return f"{t.sheet_or_page}||{'|'.join(t.headers)}"


def _match_tables(
    old_tables: List[TableData],
    new_tables: List[TableData],
) -> List[Tuple[Optional[TableData], Optional[TableData]]]:
    """Pair tables from old and new by signature, then by positional fallback."""
    new_by_sig: Dict[str, TableData] = {}
    unmatched_new: List[TableData] = []
    for t in new_tables:
        sig = _table_signature(t)
        if sig not in new_by_sig:
            new_by_sig[sig] = t
        else:
            unmatched_new.append(t)

    pairs: List[Tuple[Optional[TableData], Optional[TableData]]] = []
    used_sigs = set()
    remaining_old: List[TableData] = []

    for t in old_tables:
        sig = _table_signature(t)
        if sig in new_by_sig and sig not in used_sigs:
            pairs.append((t, new_by_sig.pop(sig)))
            used_sigs.add(sig)
        else:
            remaining_old.append(t)

    unmatched_new.extend(new_by_sig.values())

    for old_t, new_t in zip(remaining_old, unmatched_new):
        pairs.append((old_t, new_t))
    remaining_old = remaining_old[len(unmatched_new):]
    unmatched_new = unmatched_new[len(remaining_old):]

    for t in remaining_old:
        pairs.append((t, None))
    for t in unmatched_new:
        pairs.append((None, t))

    return pairs


def _diff_single_table(
    old: TableData,
    new: TableData,
) -> List[Difference]:
    diffs: List[Difference] = []
    label = old.sheet_or_page

    if old.headers != new.headers:
        diffs.append(Difference(
            section=f"Table [{label}]",
            change_type=ChangeType.MODIFIED,
            location="Headers",
            old_value=" | ".join(old.headers),
            new_value=" | ".join(new.headers),
        ))

    max_rows = max(len(old.rows), len(new.rows))
    for r in range(max_rows):
        old_row = old.rows[r] if r < len(old.rows) else None
        new_row = new.rows[r] if r < len(new.rows) else None

        if old_row is None:
            diffs.append(Difference(
                section=f"Table [{label}]",
                change_type=ChangeType.ADDED,
                location=f"Row {r + 2}",
                new_value=" | ".join(new_row),
            ))
            continue
        if new_row is None:
            diffs.append(Difference(
                section=f"Table [{label}]",
                change_type=ChangeType.REMOVED,
                location=f"Row {r + 2}",
                old_value=" | ".join(old_row),
            ))
            continue

        max_cols = max(len(old_row), len(new_row))
        for c in range(max_cols):
            ov = old_row[c] if c < len(old_row) else ""
            nv = new_row[c] if c < len(new_row) else ""
            if ov != nv:
                col_name = (
                    old.headers[c] if c < len(old.headers) else f"Col {c + 1}"
                )
                diffs.append(Difference(
                    section=f"Table [{label}]",
                    change_type=ChangeType.MODIFIED,
                    location=f"Row {r + 2}, Column '{col_name}'",
                    old_value=ov,
                    new_value=nv,
                ))

    return diffs


def _diff_tables(
    old_tables: List[TableData],
    new_tables: List[TableData],
) -> List[Difference]:
    diffs: List[Difference] = []
    pairs = _match_tables(old_tables, new_tables)

    for old_t, new_t in pairs:
        if old_t is None and new_t is not None:
            diffs.append(Difference(
                section=f"Table [{new_t.sheet_or_page}]",
                change_type=ChangeType.ADDED,
                location="Entire table",
                new_value=f"{len(new_t.rows)} row(s), columns: {', '.join(new_t.headers)}",
            ))
        elif new_t is None and old_t is not None:
            diffs.append(Difference(
                section=f"Table [{old_t.sheet_or_page}]",
                change_type=ChangeType.REMOVED,
                location="Entire table",
                old_value=f"{len(old_t.rows)} row(s), columns: {', '.join(old_t.headers)}",
            ))
        else:
            diffs.extend(_diff_single_table(old_t, new_t))

    return diffs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare(old: DocumentContent, new: DocumentContent) -> List[Difference]:
    """Return all factual differences between *old* and *new* documents."""
    diffs: List[Difference] = []
    diffs.extend(_diff_text_blocks(old.text_blocks, new.text_blocks))
    diffs.extend(_diff_tables(old.tables, new.tables))
    return diffs
