# report-differ — Project Summary

## Overview

**`report-differ`** is a four-stage Python pipeline that mechanically compares two versions of the same business report and produces a neutral, factual diff summary. It supports PDF, Excel, and Word formats, redacts PII by default, and does not rely on any business definitions or semantic knowledge.

---

## Pipeline Flow

```
extract  →  redact  →  compare  →  summarise
```

Each stage is a standalone module. The output of one feeds directly into the next. The CLI (`cli.py`) orchestrates the full flow.

---

## What Each Module Does

### 1. `extractors.py` — Document Parsing

Parses PDF (via `pdfplumber`), Excel (via `openpyxl`), and Word (via `python-docx`) files into a unified `DocumentContent` dataclass containing:

- **`text_blocks`** — list of plain-text strings (one per paragraph or page).
- **`tables`** — list of `TableData` objects, each carrying a location label, a header row, and data rows.
- **`metadata`** — any metadata the format provides (PDF info dict, Word core properties).

A single `extract(path)` dispatcher routes to the correct extractor by file extension.

### 2. `redactor.py` — PII Redaction

A deterministic, regex-based PII detection and masking engine. No ML models — fast, predictable, and auditable. All detected PII is replaced with `[REDACTED]`.

**PII categories detected:**

| Category | Pattern |
|----------|---------|
| Social Security Number | `XXX-XX-XXXX` and dash/en-dash variants |
| Email address | Standard `user@domain.tld` |
| Phone number | US 10/11-digit with optional country code, parentheses, separators |
| Credit/debit card | 13–19 digit sequences validated by the **Luhn algorithm** (rejects false positives) |
| IPv4 address | Dotted-quad `0.0.0.0` – `255.255.255.255` |
| Date of birth | Dates preceded by "DOB", "Date of Birth", or "Birth Date" labels |
| US street address | Number + street name + street-type keyword (St, Ave, Blvd, etc.) |
| Person name (labelled) | Capitalised names following labels like "Prepared by:", "Author:", "Contact:" |

Implementation highlights:
- Patterns are ordered longest/most-specific first to avoid partial matches.
- Overlapping spans are merged (longest wins).
- Replacement is performed right-to-left so character offsets remain valid.
- `redact_rows()` convenience function handles table cell matrices in one call.

### 3. `differ.py` — Structural Diff Engine

Compares two `DocumentContent` objects and produces a typed list of `Difference` records.

**Text comparison:**
- Joins all text blocks, splits into lines, and runs Python's `difflib.SequenceMatcher` with `autojunk=False`.
- Each opcode (`replace`, `insert`, `delete`) becomes a `Difference` with old/new snippets and a line-number location.

**Table comparison:**
- Tables are paired by a **signature** = `sheet_or_page || header1 | header2 | …`. Exact-match first, then positional fallback for unpaired tables.
- Paired tables are compared row-by-row, cell-by-cell. Unpaired tables are reported as entirely added or removed.
- Header changes are reported separately from data changes.

Every `Difference` record contains:
- `section` — "Text" or "Table [label]"
- `change_type` — `ADDED`, `REMOVED`, or `MODIFIED`
- `location` — human-readable position (line range, row/column)
- `old_value` / `new_value` — the actual content that changed

### 4. `summariser.py` — Summary Generation

Converts the list of `Difference` records into readable output. Two formats:

- **Plain text** — grouped by section, with `+` / `-` / `~` markers and indented old/new values. Long values are capped at 120 characters.
- **JSON** — structured array of difference objects with a `total_changes` count, suitable for downstream automation.

### 5. `cli.py` — CLI Orchestration

Wires the full pipeline behind an `argparse` interface.

Flags:
- `--format plain|json` — output format (default: `plain`)
- `--no-redact` — skip PII redaction (not recommended for production)
- `--output FILE` — write to file instead of stdout
- `--llm openai|anthropic` — (Phase 2) run the mechanical diff through an LLM for a more polished, categorised analysis
- `--llm-model MODEL` — (Phase 2) override the default model name

---

## Project Structure

```
report-differ/
├── requirements.txt
├── README.md
├── summary.md              ← this file
├── report_differ/
│   ├── __init__.py
│   ├── __main__.py          # enables `python -m report_differ`
│   ├── extractors.py        # document parsing → DocumentContent
│   ├── redactor.py          # PII detection & masking
│   ├── differ.py            # structural diff engine
│   ├── summariser.py        # neutral summary generation
│   ├── llm_analyser.py      # Phase 2 — LLM-enhanced analysis
│   └── cli.py               # CLI argument handling & orchestration
└── tests/
    ├── create_fixtures.py   # generates sample v1/v2 test files
    └── fixtures/            # auto-generated .xlsx and .docx pairs
```

---

## Design Principles

- **No hallucination** — output is derived mechanically from extracted content. Every reported difference is directly traceable to content present in the source files.
- **No business semantics** — the tool does not know what "revenue" or "net income" means. It reports that a cell changed from X to Y, period.
- **PII-safe by default** — redaction runs before comparison, so sensitive data never appears in the diff output unless explicitly opted out.
- **Format-agnostic pipeline** — extractors normalise everything into `DocumentContent`; the diff engine and summariser are format-unaware.

---

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Compare two PDFs (PII redacted by default)
python -m report_differ old_report.pdf new_report.pdf

# Compare Excel files, JSON output
python -m report_differ v1.xlsx v2.xlsx --format json

# Compare Word docs, write result to file
python -m report_differ v1.docx v2.docx -o diff_summary.txt

# Skip PII redaction
python -m report_differ old.xlsx new.xlsx --no-redact

# Phase 2 — LLM-enhanced analysis (requires API key in env)
python -m report_differ v1.xlsx v2.xlsx --llm openai
python -m report_differ v1.docx v2.docx --llm anthropic --llm-model claude-sonnet-4-20250514
```

---

## Dependencies

| Package | Purpose | Phase |
|---------|---------|-------|
| `pdfplumber` | PDF text and table extraction | 1 |
| `openpyxl` | Excel `.xlsx` reading | 1 |
| `python-docx` | Word `.docx` reading | 1 |
| `Pillow` | Image support (pdfplumber dependency) | 1 |
| `openai` | OpenAI API client (optional) | 2 |
| `anthropic` | Anthropic API client (optional) | 2 |

All other modules (`difflib`, `re`, `json`, `argparse`, `dataclasses`) are Python standard library.

---

## Phase 2 — LLM-Enhanced Analysis

The `llm_analyser.py` module adds an optional AI layer on top of the mechanical diff. It takes the already-computed, PII-redacted differences and sends them to an LLM with a tightly constrained prompt that instructs the model to:

1. **Only reference facts present in the diff data** — no outside knowledge, no assumptions.
2. **Categorise** each change (numeric, textual, structural, row added/removed).
3. **Quantify** numeric shifts (absolute and percentage).
4. **Assess significance** (high / medium / low) based on magnitude alone.
5. **Produce a structured summary** with an executive overview, categorised details, and a statistical breakdown.

The LLM is used strictly as a formatting and arithmetic layer — the ground truth always comes from the mechanical diff. If the LLM call fails, the tool falls back to the standard mechanical summary automatically.
