# Agentic Prompt — Metric / KPI Extraction

Use this prompt with **ChatGPT**, **GitHub Copilot Chat**, **Claude**, or any LLM
to extract every metric, KPI, and measurable data point from a business report.
No API keys required — just copy-paste.

---

## How to use

### Option A: Manual

1. Extract the report content as JSON:

   ```bash
   python -m report_differ.extract_metrics report.xlsx --format json > extracted.json
   ```

2. Copy the **full prompt** below.
3. Replace `PASTE YOUR JSON HERE` with the contents of `extracted.json`.
4. Paste into ChatGPT / Copilot Chat / Claude and send.

### Option B: Auto-generated (recommended)

```bash
python prompts/generate_metrics_prompt.py report.xlsx > ready_to_paste.txt
```

Paste the contents of `ready_to_paste.txt` into your LLM chat.

---

## The Prompt

Copy everything between the two `---` lines below.

---

You are a metric-extraction assistant. I will give you the full extracted
content of a business report in structured JSON format. The data has already
been extracted mechanically and any PII has been redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference data that is explicitly present in the JSON I provide below.
   Do NOT use outside knowledge, business definitions, or domain expertise.

2. Do NOT hallucinate, assume, infer, or speculate. If a metric's unit or
   context is unclear, label it "unspecified" — do not guess.

3. Your job is to identify every distinct metric, KPI, and measurable data
   point in the document. A "metric" is any labelled or contextualised numeric
   value — including currencies, percentages, counts, ratios, dates tied to
   periods, and numeric table cells with header context.

4. Produce your output using this exact structure:

   ## Document Metadata
   - Filename, format, pages/slides, text lines, word count, tables.
   - All dates and time periods found.
   - Any file-level metadata (author, title, etc.).

   ## Inline Metrics (from text)
   For each metric found in text lines, list:
   - **Label** — the text label or context preceding the number.
   - **Value** — the exact numeric value as it appears.
   - **Parsed value** — the number in standard form (e.g. "$1.2M" → 1,200,000).
   - **Unit** — currency code, "percent", "ratio", "count", or "unspecified".
   - **Source** — the exact line it was extracted from.

   ## Tabular Metrics (from tables)
   For each table, reproduce it as a markdown table and then list every numeric
   cell as a metric:
   - **Row label** (first column or row index) + **Column header** → **Value**.

   ## KPI Summary Table
   A consolidated markdown table of ALL metrics (inline + tabular) with columns:
   | # | Label | Value | Unit | Source (text line / table location) |

   ## Statistics
   - Total metrics found.
   - Breakdown: inline vs tabular.
   - Breakdown by unit type (currency, percent, ratio, count, unspecified).

5. Use neutral, factual language. No subjective adjectives.

6. Every value you quote MUST appear verbatim in the JSON input. Double-check
   each number against the source data.

7. **Accuracy is paramount.** Missing a metric is better than inventing one.

---

**Here is the extracted report data. Extract all metrics now following the rules above.**

```json
PASTE YOUR JSON HERE
```

---

## Tips for GitHub Copilot Chat

- In VS Code, open Copilot Chat (Ctrl+I / Cmd+I) and paste the full prompt.
- For large reports, save `ready_to_paste.txt` and reference it:
  `#file:ready_to_paste.txt extract all metrics following the instructions`.
- You can also use `@workspace` context: `@workspace #file:ready_to_paste.txt`.
