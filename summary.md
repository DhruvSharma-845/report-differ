# report-differ — Project Summary

## Overview

**`report-differ`** is a modular Python toolkit that can **compare two versions** of a business report (diff), **summarise a single report**, or **extract metadata, KPIs, and metrics** — producing concise, neutral, factual output. It supports PDF, Excel, Word, and PowerPoint formats, redacts PII by default, and does not rely on any business definitions or semantic knowledge.

---

## Pipeline Flows

### Diff (two-document comparison)

```
extract  →  redact  →  compare  →  summarise
```

### Summarise (single-document overview)

```
extract  →  redact  →  profile & summarise
```

### Extract Metrics (KPIs, metrics, and metadata)

```
extract  →  redact  →  detect metrics  →  format output
```

Each stage is a standalone module. The CLI orchestrates the full flow.

---

## What Each Module Does

### 1. `extractors.py` — Document Parsing

Parses PDF (via `pdfplumber`), Excel (via `openpyxl`), Word (via `python-docx`), and PowerPoint (via `python-pptx`) files into a unified `DocumentContent` dataclass containing:

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

### 5. `report_summariser.py` — Single-Report Summary (Code-Based)

Accepts a `DocumentContent` object and produces an extractive, factual summary:

- **Key factual lines** — lines containing numbers, currency amounts, dates, or
  percentages are identified via regex and surfaced verbatim as high-information
  content.
- **Table profiles** — for each table: location, headers, row count, and for
  numeric columns: min, max, and sum.
- **Full data reproduction** — tables with 20 or fewer rows are reproduced
  row-by-row so every data point is visible.
- **Two output formats** — plain text or JSON.

No LLM, no interpretation — purely extractive.

### 6. `llm_report_summariser.py` — Single-Report Summary (LLM-Enhanced)

Sends the extracted, PII-redacted document content to an LLM (OpenAI or
Anthropic) with a tightly constrained prompt that demands:

- Only reference data present in the JSON input.
- Quote every number exactly as it appears.
- Produce structured output: Document Overview, Key Figures, Text Content
  Summary, Table Summaries, and Structural Overview.
- Accuracy checks: the prompt instructs the model to double-check every number
  against the source JSON.

Falls back to the mechanical summary if the LLM call fails.

### 7. `cli.py` — CLI for Diff

Wires the diff pipeline behind an `argparse` interface.

Flags:
- `--format plain|json` — output format (default: `plain`)
- `--no-redact` — skip PII redaction (not recommended for production)
- `--output FILE` — write to file instead of stdout
- `--llm openai|anthropic` — LLM-enhanced diff analysis
- `--llm-model MODEL` — override the default model name

### 8. `summarise_report.py` — CLI for Summarise

Separate CLI for single-report summarisation.

Flags:
- `--format plain|json` — output format (default: `plain`)
- `--no-redact` — skip PII redaction
- `--output FILE` — write to file instead of stdout
- `--llm openai|anthropic` — LLM-enhanced summary
- `--llm-model MODEL` — override the default model name

### 9. `metric_extractor.py` — KPI / Metric Extraction (Code-Based)

Scans extracted document content and identifies three categories:

- **Document metadata** — file properties, structure stats, all dates found.
- **Inline metrics** — labelled numeric values detected in text via regex
  (e.g. "Revenue: $1.2M", "Growth: 14%", "LTV/CAC Ratio: 19.3:1"). Each
  metric is extracted with its label, raw value, parsed numeric value, unit
  (USD/EUR/GBP/percent/ratio/number), and source line number.
- **Tabular metrics** — every numeric cell in every table, enriched with the
  column header and row label for context.

Detection patterns:
- `Label: $1,234.56` or `Label = 14.5%` (labelled metric)
- Currency amounts with symbol ($, €, £, ¥, ₹)
- Percentages, ratios (X:Y)
- Multiplier suffixes (K, M, B, million, billion, thousand)

### 10. `llm_metric_extractor.py` — KPI / Metric Extraction (LLM-Enhanced)

Sends extracted, PII-redacted content to an LLM with a strict prompt that:
- Identifies metrics the regex engine might miss (split across lines, implied
  units, composite KPIs in prose).
- Produces a consolidated KPI summary table.
- Falls back to mechanical extraction if the LLM call fails.

### 11. `extract_metrics.py` — CLI for Metric Extraction

CLI entry point for the metric extraction capability.

Flags:
- `--format plain|json` — output format (default: `plain`)
- `--no-redact` — skip PII redaction
- `--output FILE` — write to file instead of stdout
- `--llm openai|anthropic` — LLM-enhanced extraction
- `--llm-model MODEL` — override the default model name

---

## Project Structure

```
report-differ/
├── requirements.txt
├── README.md
├── summary.md                   ← this file
├── report_differ/
│   ├── __init__.py
│   ├── __main__.py              # enables `python -m report_differ`
│   ├── extractors.py            # document parsing → DocumentContent
│   ├── redactor.py              # PII detection & masking
│   ├── differ.py                # structural diff engine
│   ├── summariser.py            # diff summary generation
│   ├── report_summariser.py     # single-report summary (code-based)
│   ├── llm_analyser.py          # LLM-enhanced diff analysis (API)
│   ├── llm_report_summariser.py # LLM-enhanced report summary (API)
│   ├── metric_extractor.py      # KPI / metric extraction (code-based)
│   ├── llm_metric_extractor.py  # LLM-enhanced metric extraction (API)
│   ├── cli.py                   # CLI for diff command
│   ├── summarise_report.py      # CLI for summarise command
│   └── extract_metrics.py       # CLI for metric extraction
├── prompts/
│   ├── phase2_prompt.md             # copy-paste prompt for diff analysis
│   ├── generate_prompt.py           # auto-generates diff analysis prompt
│   ├── summarise_prompt.md          # copy-paste prompt for report summary
│   ├── generate_summary_prompt.py   # auto-generates report summary prompt
│   ├── metrics_prompt.md            # copy-paste prompt for metric extraction
│   └── generate_metrics_prompt.py   # auto-generates metric extraction prompt
└── tests/
    ├── create_fixtures.py       # generates sample test files
    └── fixtures/                # auto-generated .xlsx and .docx pairs
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

# ── Diff (two-document comparison) ────────────────────
python -m report_differ.cli old_report.pdf new_report.pdf
python -m report_differ.cli v1.xlsx v2.xlsx --format json
python -m report_differ.cli v1.docx v2.docx -o diff_summary.txt
python -m report_differ.cli v1.xlsx v2.xlsx --llm openai

# Generate copy-paste prompt for GPT / Copilot Chat
python prompts/generate_prompt.py v1.xlsx v2.xlsx > ready_to_paste.txt

# ── Summarise (single-report overview) ────────────────
python -m report_differ.summarise_report report.xlsx
python -m report_differ.summarise_report report.pdf --format json
python -m report_differ.summarise_report report.docx --llm openai

# Generate copy-paste prompt for GPT / Copilot Chat
python prompts/generate_summary_prompt.py report.xlsx > ready_to_paste.txt

# ── Extract Metrics (KPIs and metadata) ──────────────
python -m report_differ.extract_metrics report.xlsx
python -m report_differ.extract_metrics deck.pptx --format json
python -m report_differ.extract_metrics report.pdf --llm openai

# Generate copy-paste prompt for GPT / Copilot Chat
python prompts/generate_metrics_prompt.py report.xlsx > ready_to_paste.txt
```

---

## Dependencies

| Package | Purpose | Phase |
|---------|---------|-------|
| `pdfplumber` | PDF text and table extraction | 1 |
| `openpyxl` | Excel `.xlsx` reading | 1 |
| `python-docx` | Word `.docx` reading | 1 |
| `python-pptx` | PowerPoint `.pptx` reading | 1 |
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

### Phase 2 — Copy-Paste Workflow (no API key needed)

If you prefer to use **ChatGPT**, **GitHub Copilot Chat**, or **Claude** via
their web/IDE interfaces instead of setting up API keys, the `prompts/` folder
provides everything you need:

- **`prompts/phase2_prompt.md`** — the full prompt template with instructions.
  Copy it, paste it into your LLM chat, and replace the placeholder with your
  JSON diff output.

- **`prompts/generate_prompt.py`** — a helper script that runs the mechanical
  diff and embeds the results directly into the prompt, producing a single
  ready-to-paste text blob:

  ```bash
  python prompts/generate_prompt.py v1.xlsx v2.xlsx > ready_to_paste.txt
  ```

  Then paste the contents of `ready_to_paste.txt` into ChatGPT, Copilot Chat,
  or any other LLM interface.

This gives you three ways to use Phase 2 for **both diff and summarise**:

| Method | Requires API key? | How |
|--------|-------------------|-----|
| `--llm openai` | Yes (`OPENAI_API_KEY`) | Fully automated via CLI |
| `--llm anthropic` | Yes (`ANTHROPIC_API_KEY`) | Fully automated via CLI |
| `generate_prompt.py` / `generate_summary_prompt.py` | No | Generates prompt → you paste into GPT / Copilot Chat |

---

## Single-Report Summarisation

The `report_summariser.py` module adds the ability to produce a factual overview
of a single document.  The summary is purely extractive:

- **Key factual lines** — every line containing numbers, currency, dates, or
  percentages is surfaced verbatim.
- **Table profiles** — location, headers, row count, and numeric column
  statistics (min, max, sum).
- **Full data** — tables with ≤ 20 rows are reproduced row-by-row.

For higher accuracy, the `llm_report_summariser.py` module or the copy-paste
prompt (`prompts/summarise_prompt.md`) can send the extracted data to an LLM
with strict grounding rules that forbid hallucination and require every quoted
number to appear verbatim in the source data.
