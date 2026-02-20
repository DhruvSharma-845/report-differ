# Agentic Prompt — Single-Report Summary

Use this prompt with **ChatGPT**, **GitHub Copilot Chat**, **Claude**, or any LLM
to get an accurate, structured summary of a single business report.
No API keys required — just copy-paste.

---

## How to use

### Option A: Manual

1. Extract and redact the report content as JSON:

   ```bash
   python -m report_differ.summarise_report report.xlsx --format json > extracted.json
   ```

2. Copy the **full prompt** from below.
3. Replace `PASTE YOUR JSON HERE` with the contents of `extracted.json`.
4. Paste everything into ChatGPT / Copilot Chat / Claude and send.

### Option B: Auto-generated (recommended)

```bash
python prompts/generate_summary_prompt.py report.xlsx > ready_to_paste.txt
```

Paste the contents of `ready_to_paste.txt` into your LLM chat.

---

## The Prompt

Copy everything between the two `---` lines below.

---

You are a document-summarisation assistant. I will give you the full extracted
content of a business report in structured JSON format. The data has already
been extracted mechanically from the original file and any PII has been
redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference information that is explicitly present in the JSON data I
   provide below. Do NOT use outside knowledge, business definitions, domain
   expertise, or prior training data about any company, product, or industry.

2. Do NOT hallucinate, assume, infer, or speculate about anything not in the
   data. If something is ambiguous or incomplete, state "data not available"
   rather than guess.

3. Do NOT interpret what any figure means for the business. Report WHAT the
   document contains, not WHAT it implies.

4. Produce your output using this exact structure:

   ## Document Overview
   - Filename, format, and metadata (author, title, etc.) if available.
   - Number of text lines, approximate word count, number of tables.

   ## Key Figures
   List every distinct number, currency amount, percentage, and date that
   appears in the text or tables. For each, state:
   - The exact value as it appears in the data.
   - The context it came from (which text line, or which table/row/column).
   Group them by section (Text vs each Table).

   ## Text Content Summary
   Summarise the text content in 3-5 concise bullet points. Each bullet
   must quote or closely paraphrase an actual line from the data — do NOT
   add information that isn't there.

   ## Table Summaries
   For each table:
   - Location / sheet name.
   - Column headers.
   - Row count.
   - For numeric columns: min, max, and total.
   - Reproduce the full table data as a readable markdown table.

   ## Structural Overview
   One short paragraph describing the overall structure of the document
   (e.g. "The document contains 6 paragraphs of text followed by 1 table
   with 3 columns and 2 data rows").

5. Use neutral, factual language only. No subjective adjectives like
   "impressive", "strong", "concerning", "notable", or "significant".

6. Every piece of data you reference MUST appear verbatim in the JSON below.
   If you cannot find it there, do not mention it.

7. **Accuracy is paramount.** Double-check every number you quote against the
   source JSON. If a number does not exist in the JSON, do not include it.
   If two numbers are close but not identical, use the exact value from the
   JSON.

---

**Here is the extracted report data. Summarise it now following the rules above.**

```json
PASTE YOUR JSON HERE
```

---

## Tips for GitHub Copilot Chat

- Open Copilot Chat in VS Code (Ctrl+I / Cmd+I).
- If the prompt is too long, save `ready_to_paste.txt` and reference it:
  `#file:ready_to_paste.txt summarise this report following the instructions`.
- For best results paste the JSON inline rather than referencing file paths.
- You can also use `@workspace` context: `@workspace #file:ready_to_paste.txt`
  then ask it to follow the instructions in the file.
