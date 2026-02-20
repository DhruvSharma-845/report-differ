"""Generate minimal test fixtures (two .xlsx and two .docx files) for smoke-testing."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
from docx import Document

OUT = os.path.join(os.path.dirname(__file__), "fixtures")
os.makedirs(OUT, exist_ok=True)


def make_excel():
    # --- Version 1 ---
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.title = "Revenue"
    ws1.append(["Region", "Q1", "Q2", "Q3", "Q4"])
    ws1.append(["North", "120000", "135000", "128000", "142000"])
    ws1.append(["South", "98000", "102000", "97000", "105000"])
    ws1.append(["Contact: John Smith", "Email: john@example.com", "SSN: 123-45-6789", "", ""])
    wb1.save(os.path.join(OUT, "report_v1.xlsx"))

    # --- Version 2 ---
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.title = "Revenue"
    ws2.append(["Region", "Q1", "Q2", "Q3", "Q4"])
    ws2.append(["North", "120000", "138000", "128000", "145000"])
    ws2.append(["South", "98000", "102000", "99000", "105000"])
    ws2.append(["East", "75000", "78000", "81000", "83000"])
    ws2.append(["Contact: Jane Doe", "Email: jane@example.com", "SSN: 987-65-4321", "", ""])
    wb2.save(os.path.join(OUT, "report_v2.xlsx"))


def make_word():
    # --- Version 1 ---
    d1 = Document()
    d1.add_heading("Quarterly Financial Summary", level=1)
    d1.add_paragraph("Prepared by: Alice Johnson")
    d1.add_paragraph("Total revenue for the period was $503,000.")
    d1.add_paragraph("Operating expenses totalled $312,000.")
    d1.add_paragraph("Net income: $191,000.")
    d1.add_paragraph("Contact: 555-123-4567 | alice@corp.com")

    t1 = d1.add_table(rows=3, cols=3)
    t1.rows[0].cells[0].text = "Category"
    t1.rows[0].cells[1].text = "Budget"
    t1.rows[0].cells[2].text = "Actual"
    t1.rows[1].cells[0].text = "Marketing"
    t1.rows[1].cells[1].text = "50000"
    t1.rows[1].cells[2].text = "48000"
    t1.rows[2].cells[0].text = "Engineering"
    t1.rows[2].cells[1].text = "120000"
    t1.rows[2].cells[2].text = "118000"

    d1.save(os.path.join(OUT, "summary_v1.docx"))

    # --- Version 2 ---
    d2 = Document()
    d2.add_heading("Quarterly Financial Summary", level=1)
    d2.add_paragraph("Prepared by: Bob Williams")
    d2.add_paragraph("Total revenue for the period was $527,000.")
    d2.add_paragraph("Operating expenses totalled $318,000.")
    d2.add_paragraph("Net income: $209,000.")
    d2.add_paragraph("Contact: 555-987-6543 | bob@corp.com")

    t2 = d2.add_table(rows=4, cols=3)
    t2.rows[0].cells[0].text = "Category"
    t2.rows[0].cells[1].text = "Budget"
    t2.rows[0].cells[2].text = "Actual"
    t2.rows[1].cells[0].text = "Marketing"
    t2.rows[1].cells[1].text = "55000"
    t2.rows[1].cells[2].text = "53000"
    t2.rows[2].cells[0].text = "Engineering"
    t2.rows[2].cells[1].text = "120000"
    t2.rows[2].cells[2].text = "122000"
    t2.rows[3].cells[0].text = "Sales"
    t2.rows[3].cells[1].text = "80000"
    t2.rows[3].cells[2].text = "79000"

    d2.save(os.path.join(OUT, "summary_v2.docx"))


if __name__ == "__main__":
    make_excel()
    make_word()
    print("Fixtures created in", OUT)
