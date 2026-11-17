import re
import sys
from pathlib import Path

import pymupdf

REPORTS = Path("data/downloaded_reports")  # run from the project root

_SECTION_2_HEADING = r"^Section 2:[ \t]*$"
_ROW_START = re.compile(r"(Registration|Regulation)\b")
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
_FOOTER = re.compile(r"Page \d+ of \d+")
_HAS_DIGIT = re.compile(r"\d")
_SUB_REF = re.compile(r"\d+(\s*\(\s*\w+\s*\))*")  # "05(6)(c)"; must start with a digit so a wrapped "(3)" in a requirement is not taken
_GOOD_REF = re.compile(r"(Registration\s+)?Regulation\s*\d+(\s*\(\s*\w+\s*\))*")
_HEADER_WORDS = {"Regulatory", "requirement", "Judgment", "Risk", "rating", "Date to be", "complied with"}
_JUDGMENT_WORDS = {"not", "substantially", "compliant", "not compliant", "substantially compliant"}  # lowercase
_RISKS = {"Yellow", "Orange", "Red"}


def find_section_2_page(doc: pymupdf.Document) -> int:
    pattern = re.compile(_SECTION_2_HEADING, re.MULTILINE)
    for i, page in enumerate(doc):
        if pattern.search(page.get_text()):
            return i
    raise ValueError("'Section 2:' heading not found")


def raw_rows(doc: pymupdf.Document, start: int) -> list[list[str]]:
    """Every table row from the Section 2 page to the end, cells cleaned ('' for empty, one line each)."""
    rows = []
    for page in doc[start:]:
        tables = page.find_tables().tables
        for table in tables:
            for row in table.extract():
                rows.append([" ".join(cell.split()) if cell else "" for cell in row])
        if not tables:
            # find_tables misses a page that only holds the tail of the last row (84 of 332 reports):
            # read its text lines as continuation cells, merge_rows attaches them to the previous row
            for line in page.get_text().splitlines():
                line = " ".join(line.split())
                if line and not _FOOTER.fullmatch(line):
                    rows.append(["", line])
    return rows


def merge_rows(rows: list[list[str]]) -> list[dict]:
    """One dict per regulation row. A row whose first cell is not 'Regulation...'/'Registration...' continues the previous one."""
    merged = []
    for cells in rows:
        if any(cell in _HEADER_WORDS for cell in cells):
            continue
        first, *rest = cells  # first cell = reference column; the rest are read by content, not position
        if _ROW_START.match(first):
            merged.append({"ref": [], "requirement": [], "judgment": [], "risk": None, "date": None})
        elif not merged:
            continue  # stray cells before the first regulation row
        row = merged[-1]
        if first:
            row["ref"].append(first)
        for cell in rest:
            if not cell:
                continue
            if not _HAS_DIGIT.search(" ".join(row["ref"])) and _SUB_REF.fullmatch(cell):
                row["ref"].append(cell)  # the reference was cut after the word "Regulation"; this is its tail, e.g. "05(6)(c)"
            elif cell.lower() in _JUDGMENT_WORDS:
                row["judgment"].append(cell)
            elif cell in _RISKS:
                row["risk"] = cell
            elif _DATE.fullmatch(cell):
                row["date"] = cell
            else:
                row["requirement"].append(cell)
    return [
        {
            "ref": " ".join(r["ref"]),
            "requirement": " ".join(r["requirement"]),
            "judgment": " ".join(r["judgment"]),
            "risk": r["risk"],
            "date": r["date"],
        }
        for r in merged
    ]


def table_rows(pdf_name: str) -> list[dict]:
    with pymupdf.open(REPORTS / pdf_name) as doc:
        return merge_rows(raw_rows(doc, find_section_2_page(doc)))


# (pdf, text inside the ref, expected judgment, risk, date)
CHECKS = [
    ("DIS_2024_2375-coolfin-24-october-2024.pdf", "09(3)", "Substantially Compliant", "Yellow", "31/05/2025"),
    ("DIS_2023_1507-st-dominics-services-18-october-2023.pdf", "29(4)(a)", "Substantially Compliant", "Yellow", "07/11/2023"),
    ("NH_2024_4589-sancta-maria-nursing-home-2-october-2024.pdf", "28(2)(i)", "Not Compliant", "Orange", "28/02/2025"),
    ("DIS_2026_3591-arranmore-21-january-2026.pdf", "04(3)", "Substantially Compliant", "Yellow", "27/02/2026"),
    ("NH_2023_5406-aperee-living-camp-1-august-2023.pdf", "23(a)", "Not Compliant", "Orange", None),
    ("DIS_2026_3505-peamount-healthcare-neurological-disability-service-22-january-2026.pdf", "23(2)(b)", "Substantially Compliant", None, "11/06/2026"),
okay    ("NH_2026_485-baltinglass-community-hospital-19-january-2026.pdf", "7(3)", "Not Compliant", None, "01/09/2026"),
    ("DIS_2023_5700-teach-michel-services-05-september-2023.pdf", "05(6)(c)", "Substantially Compliant", "Yellow", "11/09/2023"),
]


def bad_refs() -> list[tuple[str, str]]:
    """Every row of every report whose ref is not 'Regulation N(...)': a layout this extractor does not understand."""
    bad = []
    for pdf in sorted(REPORTS.glob("*.pdf")):
        with pymupdf.open(pdf) as doc:
            try:
                find_section_2_page(doc)
            except ValueError:
                continue  # no compliance plan
        bad += [(pdf.name, r["ref"]) for r in table_rows(pdf.name) if not _GOOD_REF.fullmatch(r["ref"])]
    return bad


if __name__ == "__main__":
    for pdf, ref_part, judgment, risk, date in CHECKS:
        rows = table_rows(pdf)
        found = [r for r in rows if ref_part in r["ref"]]
        got = (found[0]["judgment"], found[0]["risk"], found[0]["date"]) if found else None
        status = "OK  " if len(found) == 1 and got == (judgment, risk, date) else "FAIL"
        print(f"{status} {pdf[:40]:40} {ref_part:9} rows={len(rows):2} found={len(found)} got={got} expected={(judgment, risk, date)}")
    if "--all" in sys.argv:  # slow: every report
        print("rows with a bad ref:", bad_refs())
