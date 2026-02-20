# Phase 2 — LLM Prompt for Report Diff Analysis

Use this prompt with **ChatGPT**, **GitHub Copilot Chat**, **Claude**, or any LLM.
No API keys required — just copy-paste.

---

## How to use

### Option A: Manual copy-paste

1. Run the mechanical diff in JSON format:

   ```bash
   python -m report_differ v1.xlsx v2.xlsx --format json > diff_output.json
   ```

2. Copy the **full prompt** from the section below.
3. Open ChatGPT / Copilot Chat / Claude.
4. Paste the prompt.
5. At the bottom where it says `PASTE YOUR JSON DIFF DATA HERE`, replace that
   line with the contents of `diff_output.json`.
6. Send.

### Option B: Auto-generated prompt (recommended)

Run the helper script to produce a single ready-to-paste file with your diff
data already embedded:

```bash
python prompts/generate_prompt.py v1.xlsx v2.xlsx > ready_to_paste.txt
```

Then paste the entire contents of `ready_to_paste.txt` into your LLM chat.

---

## The Prompt

Copy everything between the two `---` lines below.

---

You are a document-comparison assistant. I will give you a structured JSON list
of factual differences between two versions of the same business report. The
data has already been extracted mechanically and any PII has been redacted.

**You MUST follow ALL of these rules strictly:**

1. ONLY reference facts that are explicitly present in the JSON diff data I
   provide below. Do NOT use any outside knowledge, business definitions, or
   domain expertise.

2. Do NOT hallucinate, assume, infer, or speculate about anything that is not
   in the data. If something is unclear, state "insufficient data" — do not
   guess.

3. Do NOT interpret what any change means for the business. Report WHAT changed,
   not WHY it changed or what it implies.

4. For any change where both old_value and new_value are numeric, compute:
   - The absolute difference (new − old).
   - The percentage change relative to the old value: ((new − old) / old) × 100.
   Show both numbers.

5. Categorise each change as exactly one of:
   - **NUMERIC** — both old and new values are numbers.
   - **TEXTUAL** — one or both values are non-numeric text.
   - **STRUCTURAL** — a row, column, or entire table was added or removed.
   - **HEADER** — the table header row itself changed.

6. Assess the magnitude of each change:
   - **HIGH** — numeric change >20%, or a large structural change (entire
     table / multiple rows added or removed).
   - **MEDIUM** — numeric change between 5% and 20%.
   - **LOW** — numeric change <5%, or a minor text edit.

7. Produce your output using this exact structure:

   ## Executive Overview
   One short paragraph: how many total changes, and a neutral one-sentence
   characterisation of the mix (e.g. "5 changes detected: 3 numeric, 1
   textual, 1 structural").

   ## Detailed Changes
   Group by the "section" field from the JSON (e.g. "Text", "Table [Revenue]").
   For each change, show:
   - Category tag
   - Location
   - Old value → New value
   - Absolute delta and percentage delta (numeric changes only)
   - Magnitude tag

   ## Statistics
   A summary table:
   - Total changes
   - Count by category (NUMERIC / TEXTUAL / STRUCTURAL / HEADER)
   - Count by magnitude (HIGH / MEDIUM / LOW)

8. Use neutral, factual language only. Do NOT use subjective adjectives such as
   "significant", "concerning", "impressive", "notable", "alarming", etc. Use
   the magnitude tag (HIGH / MEDIUM / LOW) instead.

9. Every piece of data you reference MUST appear verbatim in the JSON below.
   If you cannot find it there, do not mention it.

---

**Here is the diff data. Analyse it now following the rules above.**

```json
PASTE YOUR JSON DIFF DATA HERE
```

---

## Copilot Chat specific tips

- In VS Code, open Copilot Chat (Ctrl+I / Cmd+I) and paste the full prompt.
- If the prompt is too long for the chat input, save `ready_to_paste.txt` and
  use: `@workspace /explain` then paste the content, or attach the file via
  `#file:ready_to_paste.txt` in Copilot Chat.
- Copilot Chat works best when you paste the JSON inline rather than
  referencing a file path.
