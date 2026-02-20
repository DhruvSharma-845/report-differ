# report-differ

Automated tool that compares two versions of the same business report and generates a concise, neutral summary of every visible factual difference — without relying on business definitions, semantic knowledge, or any AI/LLM inference.

---

## What was built

### Problem

When a business report is revised (quarterly financials, operational summaries, etc.), stakeholders need a quick, reliable answer to *"what actually changed between version 1 and version 2?"* — free of opinion, interpretation, or hallucinated context.

### Solution

A four-module Python pipeline that:

1. **Extracts** structured content (text paragraphs + tables) from PDF, Excel, and Word files into a single normalised representation.
2. **Redacts** personally identifiable information before any comparison takes place, so PII never leaks into the diff output.
3. **Diffs** the two extracted documents mechanically — line-level for text, cell-level for tables — producing a typed list of `ADDED / REMOVED / MODIFIED` records.
4. **Summarises** those records into a concise, neutral report in plain text or JSON.

No LLM is used at any stage. Every difference reported is directly traceable to content present in the source files.

---

## Supported formats

| Format | Extension | Extraction library |
|--------|-----------|--------------------|
| PDF    | `.pdf`    | `pdfplumber`       |
| Excel  | `.xlsx`   | `openpyxl`         |
| Word   | `.docx`   | `python-docx`      |

---

## Project structure

```
report-differ/
├── requirements.txt
├── README.md
├── report_differ/
│   ├── __init__.py
│   ├── __main__.py        # enables `python -m report_differ`
│   ├── extractors.py      # document parsing → DocumentContent
│   ├── redactor.py        # PII detection & masking
│   ├── differ.py          # structural diff engine
│   ├── summariser.py      # neutral summary generation
│   └── cli.py             # CLI argument handling & orchestration
└── tests/
    ├── create_fixtures.py # generates sample v1/v2 test files
    └── fixtures/          # auto-generated .xlsx and .docx pairs
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

# Compare two PDFs (PII redacted by default)
python -m report_differ old_report.pdf new_report.pdf

# Compare Excel files, JSON output
python -m report_differ v1.xlsx v2.xlsx --format json

# Compare Word docs, write result to file
python -m report_differ v1.docx v2.docx -o diff_summary.txt

# Skip PII redaction (NOT recommended for production)
python -m report_differ old.xlsx new.xlsx --no-redact
```

### Run the included test fixtures

```bash
# Generate sample v1/v2 Excel and Word files
python tests/create_fixtures.py

# Compare the Excel pair
python -m report_differ tests/fixtures/report_v1.xlsx tests/fixtures/report_v2.xlsx

# Compare the Word pair
python -m report_differ tests/fixtures/summary_v1.docx tests/fixtures/summary_v2.docx
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
| `Pillow` | Image support (pdfplumber dependency) |

All other modules (`difflib`, `re`, `json`, `argparse`, `dataclasses`) are Python standard library.
