import re
from datetime import datetime

import pymupdf

from ingestion.models import (
    CompliancePlan,
    CompliancePlanItem,
    Judgment,
    ProviderResponse,
    RegulationSeries,
    RiskRating,
)
from ingestion.parsers.headings import COMPLIANCE_PLAN_HEADING

_SECTION_2_HEADING = r"^Section 2:[ \t]*$"  # "Section 2 is the list of..." in the intro does not match

# Section 1, one block per regulation: a heading (the title may wrap and the judgment line can sit between its lines),
# then this fixed sentence, which repeats the full title and ends at the colon. The response text runs to the next heading.
_OUTLINE = re.compile(
    r"^Outline how you are going to come into compliance with[ \t]+(Registration )?Regulation (\d+):[ \t]*([^:]+?):[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_HEADING_START = re.compile(r"^(?:Registration )?Regulation \d+:", re.MULTILINE | re.IGNORECASE)
_JUDGMENT_LINE = re.compile(
    r"^[ \t]*(Compliant|Substantially\s+compliant|Not\s+compliant)[ \t]*$", re.MULTILINE | re.IGNORECASE
)

# Section 2 is read from the PDF tables (find_tables), not from text: column positions shift between files, so cells
# are classified by content. A row that does not start with Regulation/Registration continues the previous row.
_ROW_START = re.compile(r"(Registration|Regulation)\b")
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
_FOOTER = re.compile(r"Page \d+ of \d+")
_HAS_DIGIT = re.compile(r"\d")
_SUB_REF = re.compile(r"\d+(\s*\(\s*\w+\s*\))*")  # "05(6)(c)"; must start with a digit so a wrapped "(3)" in a requirement is not taken
_REF = re.compile(r"(Registration\s+)?Regulation\s*(\d+)((?:\s*\([^)]*\))*)")
_HEADER_WORDS = {"Regulatory", "requirement", "Judgment", "Risk", "rating", "Date to be", "complied with"}
_JUDGMENT_WORDS = {"not", "substantially", "compliant", "not compliant", "substantially compliant"}  # lowercase
_RISKS = {"Yellow", "Orange", "Red"}


def parse_compliance_plan(text: str, doc: pymupdf.Document) -> CompliancePlan | None:
    """None when the report has no compliance plan (every regulation compliant), which is valid data."""
    plan = re.compile(COMPLIANCE_PLAN_HEADING, re.MULTILINE).search(text)
    if plan is None:
        return None
    section_2 = re.compile(_SECTION_2_HEADING, re.MULTILINE).search(text, plan.end())
    if section_2 is None:
        raise ValueError("compliance plan found but 'Section 2:' heading not found")
    return CompliancePlan(
        responses=_parse_responses(text[plan.end() : section_2.start()]),
        items=_parse_items(doc),
    )


def _parse_responses(section_1: str) -> list[ProviderResponse]:
    outlines = list(_OUTLINE.finditer(section_1))
    # a block's heading and judgment sit between the previous "Outline how..." sentence and its own; a body line that
    # starts with "Regulation N:" can come earlier in that stretch, so the real heading is the last one
    heads: list[tuple[int, str]] = []  # (where the heading starts, judgment text)
    previous_end = 0
    for outline in outlines:
        heading_start = _last_match(_HEADING_START, section_1, previous_end, outline).start()
        judgment = _last_match(_JUDGMENT_LINE, section_1, heading_start, outline).group(1)
        heads.append((heading_start, judgment))
        previous_end = outline.end()

    responses = []
    for i, outline in enumerate(outlines):
        next_outline = outlines[i + 1] if i + 1 < len(outlines) else None
        end = heads[i + 1][0] if next_outline else len(section_1)
        body = " ".join(section_1[outline.end() : end].split())
        # some reports print the whole heading block twice in a row; the first copy has no response text
        if not body and next_outline and outline.group(1, 2) == next_outline.group(1, 2):
            continue
        registration, number, title = outline.group(1), outline.group(2), " ".join(outline.group(3).split())
        responses.append(
            ProviderResponse(
                series=_series(registration),
                regulation_number=number,
                title=title,
                judgment=Judgment(heads[i][1]),
                response_text=body,
            )
        )
    return responses


def _last_match(pattern: re.Pattern[str], text: str, start: int, before: re.Match[str]) -> re.Match[str]:
    """Last match of pattern between start and the given match; a loud error beats a silently lost response."""
    found = list(pattern.finditer(text, start, before.start()))
    if not found:
        raise ValueError(f"no {pattern.pattern!r} before: {before.group(0)[:80]!r}")
    return found[-1]


def _parse_items(doc: pymupdf.Document) -> list[CompliancePlanItem]:
    return [_to_item(row) for row in _merge_rows(_raw_rows(doc, _section_2_page(doc)))]


def _section_2_page(doc: pymupdf.Document) -> int:
    pattern = re.compile(_SECTION_2_HEADING, re.MULTILINE)
    for i, page in enumerate(doc):
        if pattern.search(page.get_text()):
            return i
    raise ValueError("'Section 2:' heading not found")


def _raw_rows(doc: pymupdf.Document, start: int) -> list[list[str]]:
    """Every table row from the Section 2 page to the end, cells cleaned ('' for empty, one line each)."""
    rows = []
    for page in doc[start:]:
        tables = page.find_tables().tables
        for table in tables:
            for row in table.extract():
                rows.append([" ".join(cell.split()) if cell else "" for cell in row])
        if not tables:
            # find_tables misses a page that only holds the tail of the last row: read its lines as continuation cells
            for line in page.get_text().splitlines():
                line = " ".join(line.split())
                if line and not _FOOTER.fullmatch(line):
                    rows.append(["", line])
    return rows


def _merge_rows(rows: list[list[str]]) -> list[dict]:
    """One dict per regulation row. A row that does not start with Regulation/Registration continues the previous one."""
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
                row["ref"].append(cell)  # the ref was cut after the word "Regulation"; this is its tail, e.g. "05(6)(c)"
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


def _to_item(row: dict) -> CompliancePlanItem:
    m = _REF.fullmatch(row["ref"])
    if m is None:
        raise ValueError(f"unrecognised regulation reference: {row['ref']!r}")  # loud, like the response parser
    registration, number, sub_refs = m.groups()
    return CompliancePlanItem(
        regulation_ref=f"{'Registration ' if registration else ''}Regulation {number}{''.join(sub_refs.split())}",
        series=_series(registration),
        regulation_number=str(int(number)),  # some reports print "Regulation 05(4)(b)"
        requirement=row["requirement"],
        judgment=Judgment(row["judgment"]),
        risk_rating=RiskRating(row["risk"]) if row["risk"] else None,
        due_date=datetime.strptime(row["date"], "%d/%m/%Y").date() if row["date"] else None,
    )


def _series(registration: str | None) -> RegulationSeries:
    return RegulationSeries.REGISTRATION if registration else RegulationSeries.CARE
