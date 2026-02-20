# report-differ

Automated toolkit that **compares two versions** of a business report, **summarises a single report**, or **extracts metadata, KPIs, and metrics** — generating concise, neutral, factual output without relying on business definitions, semantic knowledge, or any AI/LLM inference.

---

## What was built

### Problem

Stakeholders need quick, reliable answers to three questions:

1. *"What actually changed between version 1 and version 2?"*
2. *"What does this report contain?"*
3. *"What are the key numbers, KPIs, and metrics in this report?"*

All answers must be free of opinion, interpretation, or hallucinated context.

### Solution

A modular Python toolkit with three capabilities:

**Capability 1 — Diff** (compare two report versions):
1. **Extracts** structured content (text paragraphs + tables) from PDF, Excel, Word, and PowerPoint files.
2. **Redacts** PII before comparison.
3. **Diffs** mechanically — line-level for text, cell-level for tables.
4. **Summarises** into a concise neutral report (plain text or JSON).

**Capability 2 — Summarise** (single-report overview):
1. **Extracts** the document into the same normalised structure.
2. **Redacts** PII.
3. **Profiles** the content — surfaces key factual lines (numbers, currency, dates, percentages), computes table column statistics (min, max, sum), and reproduces all data.
4. **Summarises** into a structured factual overview (plain text or JSON).

**Capability 3 — Extract Metrics** (KPIs, metrics, and metadata):
1. **Extracts** document content and metadata.
2. **Redacts** PII.
3. **Detects** inline metrics (labelled numbers, currency, percentages, ratios in text) and tabular metrics (numeric cells with header/row-label context).
4. **Outputs** a structured inventory of every metric found, with parsed values, units, and source locations.

All three capabilities can optionally be enhanced with an LLM (via API or copy-paste prompt) for higher-accuracy output — while the ground truth always comes from the mechanical extraction.

---

## Supported formats

| Format     | Extension | Extraction library |
|------------|-----------|--------------------|
| PDF        | `.pdf`    | `pdfplumber`       |
| Excel      | `.xlsx`   | `openpyxl`         |
| Word       | `.docx`   | `python-docx`      |
| PowerPoint | `.pptx`   | `python-pptx`      |

---

## Project structure

```
report-differ/
├── requirements.txt
├── README.md
├── summary.md
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

## Module-by-module summary

### 1. `extractors.py` — Document parsing

Reads a file path, detects its type by extension, and returns a `DocumentContent` dataclass containing:

- **`text_blocks`** — list of plain-text strings (one per paragraph/page).
- **`tables`** — list of `TableData` objects, each with a location label, a header row, and data rows.
- **`metadata`** — any metadata the format provides (PDF info dict, Word core properties).

Each format has a dedicated extractor (`extract_pdf`, `extract_excel`, `extract_word`) behind a single `extract(path)` dispatcher.

### 2. `redactor.py` — PII redaction

A deterministic, regex-based engine that scans text and replaces PII with `[REDACTED]`. No ML models — fast, predictable, and auditable.

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

Key implementation details:
- Patterns are ordered longest/most-specific first to avoid partial matches.
- Overlapping spans are merged (longest wins).
- Replacement is performed right-to-left so character offsets remain valid.
- `redact_rows()` convenience function handles table cell matrices in one call.

### 3. `differ.py` — Structural diff engine

Compares two `DocumentContent` objects and produces a list of `Difference` records.

**Text comparison:**
- Joins all text blocks, splits into lines, and runs Python's `difflib.SequenceMatcher` with `autojunk=False`.
- Each opcode (`replace`, `insert`, `delete`) becomes a `Difference` with the old/new snippets and line-number location.

**Table comparison:**
- Tables are paired by a **signature** = `sheet_or_page || header1 | header2 | …`. Exact-match first, then positional fallback for unpaired tables.
- Paired tables are compared row-by-row, cell-by-cell. Unpaired tables are reported as entirely added or removed.
- Header changes are reported separately from data changes.

Every `Difference` has:
- `section` — "Text" or "Table [label]"
- `change_type` — `ADDED`, `REMOVED`, or `MODIFIED`
- `location` — human-readable position (line range, row/column)
- `old_value` / `new_value` — the actual content that changed

### 4. `summariser.py` — Summary generation

Converts the list of `Difference` records into readable output. Two formats:

- **Plain text** — grouped by section, with `+` / `-` / `~` markers and indented old/new values. Long values are capped at 120 characters.
- **JSON** — structured array of difference objects with a `total_changes` count, suitable for downstream automation.

### 5. `cli.py` — CLI orchestration

Wires the pipeline together behind an `argparse` interface:

```
extract → redact → compare → summarise → output
```

Flags:
- `--format plain|json` — output format (default: `plain`)
- `--no-redact` — skip PII redaction (not recommended for production)
- `--output FILE` — write to file instead of stdout

---

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt
```

### Diff — compare two report versions

```bash
# Compare two PDFs (PII redacted by default)
python -m report_differ.cli old_report.pdf new_report.pdf

# Compare Excel files, JSON output
python -m report_differ.cli v1.xlsx v2.xlsx --format json

# Compare Word docs, write result to file
python -m report_differ.cli v1.docx v2.docx -o diff_summary.txt

# LLM-enhanced diff (requires API key in env)
python -m report_differ.cli v1.xlsx v2.xlsx --llm openai

# Generate a prompt to paste into GPT / Copilot Chat (no API key)
python prompts/generate_prompt.py v1.xlsx v2.xlsx > ready_to_paste.txt
```

### Summarise — get an overview of a single report

```bash
# Mechanical summary (code-based, no LLM)
python -m report_differ.summarise_report report.xlsx
python -m report_differ.summarise_report report.pdf --format json

# LLM-enhanced summary (requires API key in env)
python -m report_differ.summarise_report report.docx --llm openai

# Generate a prompt to paste into GPT / Copilot Chat (no API key)
python prompts/generate_summary_prompt.py report.xlsx > ready_to_paste.txt
```

### Extract Metrics — pull out KPIs, metrics, and metadata

```bash
# Mechanical extraction (code-based, no LLM)
python -m report_differ.extract_metrics report.xlsx
python -m report_differ.extract_metrics deck.pptx --format json

# LLM-enhanced extraction (requires API key in env)
python -m report_differ.extract_metrics report.pdf --llm openai
python -m report_differ.extract_metrics deck.pptx --llm anthropic

# Generate a prompt to paste into GPT / Copilot Chat (no API key)
python prompts/generate_metrics_prompt.py report.xlsx > ready_to_paste.txt
```

### Run the included test fixtures

```bash
# Generate sample v1/v2 Excel and Word files
python tests/create_fixtures.py

# Diff the Excel pair
python -m report_differ.cli tests/fixtures/report_v1.xlsx tests/fixtures/report_v2.xlsx

# Diff the Word pair
python -m report_differ.cli tests/fixtures/summary_v1.docx tests/fixtures/summary_v2.docx

# Summarise a single file
python -m report_differ.summarise_report tests/fixtures/report_v2.xlsx
python -m report_differ.summarise_report tests/fixtures/summary_v1.docx

# Extract metrics from a PowerPoint deck
python -m report_differ.extract_metrics tests/fixtures/deck_q3.pptx
```

---

## Design principles

- **No hallucination** — output is derived mechanically from extracted content. Nothing is inferred, assumed, or generated by a language model.
- **No business semantics** — the tool does not know what "revenue" or "net income" means. It reports that a cell value changed from X to Y.
- **PII-safe by default** — redaction runs before comparison, so sensitive data never appears in the diff output unless explicitly opted out.
- **Format-agnostic pipeline** — extractors normalise everything into `DocumentContent`; the diff engine and summariser are format-unaware.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pdfplumber` | PDF text and table extraction |
| `openpyxl` | Excel `.xlsx` reading |
| `python-docx` | Word `.docx` reading |
| `python-pptx` | PowerPoint `.pptx` reading |
| `Pillow` | Image support (pdfplumber dependency) |

All other modules (`difflib`, `re`, `json`, `argparse`, `dataclasses`) are Python standard library.
