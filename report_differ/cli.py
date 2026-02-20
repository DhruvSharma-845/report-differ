"""
CLI entry-point for report-differ.

Usage
-----
    python -m report_differ.cli old_report.pdf new_report.pdf
    python -m report_differ.cli old.xlsx new.xlsx --format json --no-redact
    python -m report_differ.cli v1.docx v2.docx --llm openai
"""

from __future__ import annotations

import argparse
import sys

from .extractors import extract, DocumentContent, TableData
from .redactor import redact, redact_rows
from .differ import compare
from .summariser import summarise


def _redact_document(doc: DocumentContent) -> DocumentContent:
    """Return a copy of *doc* with all PII replaced by [REDACTED]."""
    new_text = []
    for block in doc.text_blocks:
        redacted_text, _ = redact(block)
        new_text.append(redacted_text)

    new_tables = []
    for tbl in doc.tables:
        new_headers = [redact(h)[0] for h in tbl.headers]
        new_rows = redact_rows(tbl.rows)
        new_tables.append(TableData(
            sheet_or_page=tbl.sheet_or_page,
            headers=new_headers,
            rows=new_rows,
        ))

    return DocumentContent(
        filename=doc.filename,
        format=doc.format,
        text_blocks=new_text,
        tables=new_tables,
        metadata=doc.metadata,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="report-differ",
        description=(
            "Compare two versions of a business report and produce a concise, "
            "neutral summary of visible factual differences."
        ),
    )
    parser.add_argument("old", help="Path to the earlier version of the report")
    parser.add_argument("new", help="Path to the newer version of the report")
    parser.add_argument(
        "--format", "-f",
        choices=["plain", "json"],
        default="plain",
        help="Output format (default: plain)",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        default=False,
        help="Skip PII redaction (NOT recommended for production use)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write summary to file instead of stdout",
    )

    llm_group = parser.add_argument_group("LLM-enhanced analysis (Phase 2)")
    llm_group.add_argument(
        "--llm",
        choices=["openai", "anthropic"],
        default=None,
        help="Send mechanical diffs to an LLM for categorised analysis",
    )
    llm_group.add_argument(
        "--llm-model",
        default=None,
        help=(
            "Override the default model for the chosen provider "
            "(openai default: gpt-4o, anthropic default: claude-sonnet-4-20250514)"
        ),
    )

    args = parser.parse_args(argv)

    old_doc = extract(args.old)
    new_doc = extract(args.new)

    if not args.no_redact:
        old_doc = _redact_document(old_doc)
        new_doc = _redact_document(new_doc)

    diffs = compare(old_doc, new_doc)

    if args.llm:
        from .llm_analyser import analyse_with_llm
        summary = analyse_with_llm(diffs, provider=args.llm, model=args.llm_model)
    else:
        summary = summarise(diffs, fmt=args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(summary)
        print(f"Summary written to {args.output}", file=sys.stderr)
    else:
        print(summary)


if __name__ == "__main__":
    main()
