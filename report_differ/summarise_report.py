"""
CLI entry-point for single-report summarisation.

Usage
-----
    python -m report_differ.summarise_report report.pdf
    python -m report_differ.summarise_report report.xlsx --format json
    python -m report_differ.summarise_report report.docx --llm openai
"""

from __future__ import annotations

import argparse
import sys

from .extractors import extract, DocumentContent, TableData
from .redactor import redact, redact_rows
from .report_summariser import summarise_report


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="report-summarise",
        description=(
            "Extract and summarise a single business report. "
            "Produces an accurate, factual overview of the document's contents."
        ),
    )
    parser.add_argument("report", help="Path to the report file (PDF, Excel, or Word)")
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

    llm_group = parser.add_argument_group("LLM-enhanced summary")
    llm_group.add_argument(
        "--llm",
        choices=["openai", "anthropic"],
        default=None,
        help="Send extracted content to an LLM for a polished summary",
    )
    llm_group.add_argument(
        "--llm-model",
        default=None,
        help="Override the default model for the chosen provider",
    )

    args = parser.parse_args(argv)

    doc = extract(args.report)

    if not args.no_redact:
        doc = _redact_document(doc)

    if args.llm:
        from .llm_report_summariser import summarise_report_with_llm
        summary = summarise_report_with_llm(doc, provider=args.llm, model=args.llm_model)
    else:
        summary = summarise_report(doc, fmt=args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(summary)
        print(f"Summary written to {args.output}", file=sys.stderr)
    else:
        print(summary)


if __name__ == "__main__":
    main()
