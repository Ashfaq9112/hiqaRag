"""Corpus invariants: rules that must hold for EVERY parsed report.

Group A uses only the JSONL (internal consistency).
Group B re-counts things in the raw PDF text, which does not depend on the parser, to catch silent loss.

uv run python tests/corpus_invariants.py                     # data/parsed/reports_narr.jsonl
uv run python tests/corpus_invariants.py data/parsed/reports_400.jsonl
uv run python tests/corpus_invariants.py --no-pdf            # Group A only (fast)
"""
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so "ingestion" is the project package, not tests/ingestion

from ingestion.models import Judgment, ParsedReport, ServiceType  # noqa: E402

PDF_DIR = ROOT / "data/downloaded_reports"
DEFAULT_JSONL = ROOT / "data/parsed/reports_narr.jsonl"

_REF = re.compile(r"(Registration )?Regulation \d+(\([^)]+\))*")
_DIGITS = re.compile(r"Regulation (\d+)")
_JUDGMENT_IN_TEXT = re.compile(r"\b(Not Compliant|Substantially Compliant|Compliant)\b", re.IGNORECASE)
_RISK_IN_TEXT = re.compile(r"\b(Yellow|Orange|Red)\b")
_DATE_IN_TEXT = re.compile(r"\d{2}/\d{2}/\d{4}")
_JUDGMENT_LINE = re.compile(r"^Judgment:\s*(Not Compliant|Substantially Compliant|Compliant)", re.IGNORECASE | re.MULTILINE)
_CENTRE_ID = re.compile(r"OSV-\d{7}")
_FIELDWORK_ID = re.compile(r"MON-\d{7}")
_SEVERITY = {Judgment.COMPLIANT: 0, Judgment.SUBSTANTIALLY_COMPLIANT: 1, Judgment.NOT_COMPLIANT: 2}
_NARRATIVE_FIELDS =("how_we_inspect", "what_residents_told_us", "capacity_intro", "quality_intro")
# cover title (spaces removed, lowercase) -> the service type it must produce
_COVER_TITLES = {
    "designatedcentreforolderpeople": ServiceType.NURSING_HOME,
    "designatedcentrefordisabilities(adults)": ServiceType.DISABILITY_ADULTS,
    "designatedcentrefordisabilities(children)": ServiceType.DISABILITY_CHILDREN,
    "designatedcentrefordisabilities(mixed)": ServiceType.DISABILITY_MIXED,
}


def squeeze(text: str) -> str:
    """Lowercase with ALL whitespace removed, so labels match even where the cover text has garbled spacing."""
    return re.sub(r"\s+", "", text.lower())


def norm(text: str) -> str:
    """Lowercase, letters and digits only, so 'Persons in charge.' == 'persons  in charge'."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# ---------------------------------------------------------------- Group A: JSONL only

def check_report(r: ParsedReport) -> list[tuple[str, str]]:
    """(check name, detail) for every rule this report breaks."""
    bad: list[tuple[str, str]] = []

    # --- cover: not empty, well formed
    c = r.cover
    for name in ("centre_name", "provider", "address"):
        if not getattr(c, name).strip():
            bad.append((f"cover: empty {name}", ""))
    if not _CENTRE_ID.fullmatch(c.centre_id):
        bad.append(("cover: centre_id has the wrong format", c.centre_id))
    if not _FIELDWORK_ID.fullmatch(c.fieldwork_id):
        bad.append(("cover: fieldwork_id has the wrong format", c.fieldwork_id))
    if not date(2020, 1, 1) <= c.inspection_date <= date.today():
        bad.append(("cover: inspection_date out of range", str(c.inspection_date)))

    # --- about the centre, residents
    if not 200 <= len(r.about_centre) <= 3500:
        bad.append(("about_centre: length outside 200-3500", str(len(r.about_centre))))
    # "number of residents" alone is ordinary prose ("accommodates a number of residents"); the full label is the heading
    for heading in ("How we inspect", "Number of residents on the date of inspection"):
        if heading.lower() in r.about_centre.lower():
            bad.append(("about_centre: contains another section's heading", heading))
    if r.residents_on_date is None or not 1 <= r.residents_on_date <= 300:
        bad.append(("residents_on_date: missing or outside 1-300", str(r.residents_on_date)))

    # --- findings vs appendix: same regulations, same judgment, same category
    findings = {(f.series, f.regulation_number): f for f in r.findings}
    appendix = {(a.series, a.regulation_number): a for a in r.appendix}
    if len(findings) != len(r.findings):
        bad.append(("findings: duplicate regulation", str([k for k, n in Counter((f.series, f.regulation_number) for f in r.findings).items() if n > 1])))
    if len(appendix) != len(r.appendix):
        bad.append(("appendix: duplicate regulation", str([k for k, n in Counter((a.series, a.regulation_number) for a in r.appendix).items() if n > 1])))
    for key in sorted(appendix.keys() - findings.keys()):
        bad.append(("appendix row without finding", f"{key[0].value} {key[1]}"))
    for key in sorted(findings.keys() - appendix.keys()):
        bad.append(("finding without appendix row", f"{key[0].value} {key[1]}"))
    for key in findings.keys() & appendix.keys():
        f, a = findings[key], appendix[key]
        where = f"{key[0].value} {key[1]}"
        if f.judgment != a.judgment:
            bad.append(("finding/appendix judgment differs", f"{where}: finding={f.judgment.value} appendix={a.judgment.value}"))
        if f.dimension != a.dimension:
            bad.append(("finding/appendix dimension differs", f"{where}: finding={f.dimension.value} appendix={a.dimension.value}"))
        if norm(f.title) != norm(a.title):
            bad.append(("finding/appendix title differs", f"{where}: {f.title!r} vs {a.title!r}"))
        if not f.text.strip() and f.judgment != Judgment.COMPLIANT:  # a compliant regulation can be just a heading + "Judgment: Compliant"
            bad.append(("finding: empty text on a non-compliant regulation", where))
        if not f.regulation_number.isdigit():
            bad.append(("finding: regulation_number is not digits", f"{where}: {f.regulation_number!r}"))
        # a bare "Registration Regulation 8 (1)" heading has no title in the PDF, so an empty title is valid there
        if (not f.title.strip() and f.series.value == "care") or len(f.title) >= 120:
            bad.append(("finding: care title empty, or any title 120+ chars", f"{where}: {len(f.title)} chars"))
        if "Judgment:" in f.text:
            bad.append(("finding: text contains 'Judgment:'", where))

    # --- appendix vs compliance plan: a plan exists exactly when something is not fully compliant
    not_compliant = {k for k, a in appendix.items() if a.judgment != Judgment.COMPLIANT}
    plan = r.compliance_plan
    if plan is None:
        if not_compliant:
            bad.append(("no compliance plan, but appendix has non-compliant regulations", str(len(not_compliant))))
    else:
        if not not_compliant:
            bad.append(("compliance plan present, but appendix is all compliant", ""))
        resp_keys = [(p.series, p.regulation_number) for p in plan.responses]
        item_keys = {(i.series, i.regulation_number) for i in plan.items}
        for key, n in Counter(resp_keys).items():
            if n > 1:
                bad.append(("plan: duplicate response", f"{key[0].value} {key[1]} x{n}"))
        for key in sorted(item_keys - set(resp_keys)):
            bad.append(("plan: item without response", f"{key[0].value} {key[1]}"))
        for key in sorted(set(resp_keys) - item_keys):
            bad.append(("plan: response without item", f"{key[0].value} {key[1]}"))
        for key in sorted(not_compliant - set(resp_keys)):
            bad.append(("plan: non-compliant regulation without response", f"{key[0].value} {key[1]}"))
        for key in sorted(set(resp_keys) - not_compliant):
            bad.append(("plan: response for a regulation the appendix calls compliant", f"{key[0].value} {key[1]}"))

        # --- responses
        for p in plan.responses:
            where = f"{p.series.value} {p.regulation_number}"
            if not p.response_text.strip():
                bad.append(("response: empty text", where))
            elif "Outline how" in p.response_text or "Section 2" in p.response_text:
                bad.append(("response: text contains 'Outline how' or 'Section 2'", where))
            a = appendix.get((p.series, p.regulation_number))
            if a and p.judgment != a.judgment:
                bad.append(("response: judgment differs from appendix", f"{where}: response={p.judgment.value} appendix={a.judgment.value}"))
            if a and norm(p.title) != norm(a.title):
                bad.append(("response: title differs from appendix", f"{where}: {p.title!r} vs {a.title!r}"))

        # --- items
        for i in plan.items:
            where = i.regulation_ref
            if not _REF.fullmatch(i.regulation_ref):
                bad.append(("item: ref has the wrong format", repr(i.regulation_ref)))
            m = _DIGITS.search(i.regulation_ref)
            if m and str(int(m.group(1))) != i.regulation_number:  # the ref keeps the PDF's "05", the number is normalised to "5"
                bad.append(("item: regulation_number differs from ref", f"{where} vs {i.regulation_number}"))
            if i.regulation_ref.startswith("Registration") != (i.series.value == "registration"):
                bad.append(("item: series differs from ref", f"{where} vs {i.series.value}"))
            a = appendix.get((i.series, i.regulation_number))
            # a regulation judged "not compliant" can have sub-items that are only "substantially compliant" (143 items),
            # so a difference is fine; an item WORSE than the regulation's own judgment is not expected
            if a and _SEVERITY[i.judgment] > _SEVERITY[a.judgment]:
                bad.append(("item: judgment is worse than the appendix judgment", f"{where}: item={i.judgment.value} appendix={a.judgment.value}"))
            if len(i.requirement.strip()) < 20:
                bad.append(("item: requirement empty or tiny", f"{where}: {i.requirement!r}"))
            if _JUDGMENT_IN_TEXT.fullmatch(i.requirement.strip()) or (_DATE_IN_TEXT.search(i.requirement) and _RISK_IN_TEXT.search(i.requirement)):
                bad.append(("item: requirement contains judgment/risk/date cells", f"{where}: {i.requirement[:80]!r}"))
            if i.requirement.lstrip().startswith("("):
                bad.append(("item: requirement starts with '(' (ref tail swallowed)", f"{where}: {i.requirement[:60]!r}"))

    # --- narrative. The stored text has no newlines, so no line-start (^) rules: plain substring checks only.
    # Prose may mention "Regulation 17: Premises" legitimately, so a regulation title is NOT a failure by itself;
    # "Judgment:" is: it only appears in a finding block that was swallowed into the field.
    for name in _NARRATIVE_FIELDS:
        text = getattr(r.narrative, name)
        if not text or not text.strip():
            bad.append(("narrative: empty field", name))
        elif "Judgment:" in text:
            bad.append(("narrative: contains 'Judgment:' (a finding block was swallowed)", name))
    if r.parse_warnings:
        bad.append(("parse_warnings not empty", "; ".join(r.parse_warnings)))
    return bad


# ---------------------------------------------------------------- Group B: re-count in the PDF

def section_2_text(doc: pymupdf.Document) -> str | None:
    """Plain text of the 'Section 2:' page to the end (the regulations-to-be-complied-with table), or None."""
    for i, page in enumerate(doc):
        if re.search(r"^Section 2:[ \t]*$", page.get_text(), re.MULTILINE):
            return "\n".join(p.get_text() for p in doc[i:])
    return None


def findings_text(doc: pymupdf.Document) -> str:
    """Text before the Appendix 1 table (that is where the findings live)."""
    text = "\n".join(page.get_text() for page in doc)
    cut = re.search(r"Full list of regulations considered", text)
    return text[: cut.start()] if cut else text


def check_against_pdf(r: ParsedReport) -> list[tuple[str, str]]:
    bad: list[tuple[str, str]] = []
    pdf = PDF_DIR / r.source_file
    if not pdf.exists():
        return [("pdf missing", r.source_file)]
    with pymupdf.open(pdf) as doc:
        raw_findings = findings_text(doc)
        raw_plan = section_2_text(doc)
        page1 = squeeze(doc[0].get_text())
        whole = "\n".join(page.get_text() for page in doc)

    # --- cover: re-read the labelled values on page 1 and compare (spaces removed: the cover spacing is garbled in some files)
    m = re.search(r"typeofinspection:?(.*?)dateofinspection:?(.*?)centreid", page1)
    if not m:
        bad.append(("pdf: cover labels 'Type/Date of inspection' not found", ""))
    else:
        type_seg, date_seg = m.groups()
        d = r.cover.inspection_date
        if not (d.strftime("%B").lower() in date_seg and str(d.year) in date_seg and re.search(rf"(?<!\d)0?{d.day}(?!\d)", date_seg)):
            bad.append(("pdf: inspection_date not in the cover's date text", f"stored={d} cover={date_seg!r}"))
        if type_seg != r.cover.inspection_type.value.replace("_", ""):
            bad.append(("pdf: inspection_type differs from the cover", f"stored={r.cover.inspection_type.value} cover={type_seg!r}"))
    titles = [kind for title, kind in _COVER_TITLES.items() if title in page1]
    if len(titles) != 1:
        bad.append(("pdf: cover title not recognised", f"matches={titles}"))
    elif titles[0] != r.cover.service_type:
        bad.append(("pdf: service_type differs from the cover title", f"stored={r.cover.service_type.value} title={titles[0].value}"))

    # --- residents: independent regex over whitespace-free text
    m = re.search(r"numberofresidentsonthedateofinspection:?(\d+)", squeeze(whole))
    if not m or int(m.group(1)) != r.residents_on_date:
        bad.append(("pdf: residents_on_date differs from the PDF", f"stored={r.residents_on_date} pdf={m.group(1) if m else None}"))

    # --- appendix: one judgment per row, counted in the Appendix 1 text (up to the compliance plan, if any)
    start = whole.find("Full list of regulations considered")
    end = whole.find("Compliance Plan for", start)
    region = " ".join(whole[start : end if end != -1 else len(whole)].split())
    pdf_appendix_rows = len(re.findall(r"\b(?:Not compliant|Substantially compliant|Compliant)\b", region, re.IGNORECASE))
    if pdf_appendix_rows != len(r.appendix):
        bad.append(("pdf: appendix judgment cells != appendix rows", f"pdf={pdf_appendix_rows} parsed={len(r.appendix)}"))

    n_judgments = len(_JUDGMENT_LINE.findall(raw_findings))
    if n_judgments != len(r.findings):
        bad.append(("pdf: 'Judgment:' lines != findings", f"pdf={n_judgments} parsed={len(r.findings)}"))

    plan = r.compliance_plan
    if raw_plan is None:
        if plan is not None:
            bad.append(("pdf: no 'Section 2:' but a plan was parsed", ""))
        return bad
    if plan is None:
        return bad + [("pdf: has 'Section 2:' but no plan was parsed", "")]

    # a value in its own line = a table cell; prose that merely mentions a colour or date is ignored
    lines = [" ".join(line.split()) for line in raw_plan.splitlines()]
    pdf_dates = sum(1 for line in lines if _DATE_IN_TEXT.fullmatch(line))
    pdf_risks = sum(1 for line in lines if line in ("Yellow", "Orange", "Red"))
    # one judgment cell per row. Counting lines that start with "Regulation" would be wrong: a wrapped requirement
    # sentence can start a line with "Regulation 5(1)", and the header cell is also just "Regulation".
    pdf_rows = sum(1 for line in lines if re.fullmatch(r"(Not|Substantially)( compliant)?", line, re.IGNORECASE))
    parsed_dates = sum(1 for i in plan.items if i.due_date)
    parsed_risks = sum(1 for i in plan.items if i.risk_rating)
    if pdf_dates != parsed_dates:
        bad.append(("pdf: date cells != items with a due_date", f"pdf={pdf_dates} parsed={parsed_dates} of {len(plan.items)} items"))
    if pdf_risks != parsed_risks:
        bad.append(("pdf: risk cells != items with a risk_rating", f"pdf={pdf_risks} parsed={parsed_risks} of {len(plan.items)} items"))
    if pdf_rows != len(plan.items):
        bad.append(("pdf: judgment cells (table rows) != items", f"pdf={pdf_rows} parsed={len(plan.items)}"))
    return bad


# ---------------------------------------------------------------- loading + accepted exceptions

def load_reports(path: Path) -> list[ParsedReport]:
    with open(path, encoding="utf-8") as f:
        return [ParsedReport.model_validate_json(line) for line in f]


_WORSE = "item: judgment is worse than the appendix judgment"
# (source_file, check, detail): source-data quirks confirmed in the PDFs, not parser bugs
KNOWN_EXCEPTIONS: set[tuple[str, str, str]] = {
    ("DIS_2024_3578-glenageary-03-july-2024.pdf", "response: title differs from appendix",
     "care 7: 'Positive behavioral support' vs 'Positive behavioural support'"),
    ("DIS_2025_8831-turlough-gardens-05-september-2025.pdf", _WORSE,
     "Regulation 28(3)(d): item=not_compliant appendix=substantially_compliant"),
    ("NH_2023_266-aperee-living-churchtown-10-august-2023.pdf", _WORSE,
     "Regulation 17(2): item=not_compliant appendix=substantially_compliant"),
    ("NH_2023_5394-laurel-lodge-nursing-home-2-may-2023.pdf", _WORSE,
     "Regulation 29(6): item=not_compliant appendix=substantially_compliant"),
    ("NH_2024_186-woodlands-house-nursing-home-3-january-2024.pdf", _WORSE,
     "Regulation 20(2)(e): item=not_compliant appendix=substantially_compliant"),
    ("NH_2024_186-woodlands-house-nursing-home-3-january-2024.pdf", _WORSE,
     "Regulation 20(2)(c): item=not_compliant appendix=substantially_compliant"),
    ("NH_2024_315-ave-maria-nursing-home-18-june-2024.pdf", _WORSE,
     "Regulation 23(d): item=not_compliant appendix=substantially_compliant"),
    ("NH_2024_315-ave-maria-nursing-home-18-june-2024.pdf", _WORSE,
     "Regulation 23(e): item=not_compliant appendix=substantially_compliant"),
    ("NH_2024_315-ave-maria-nursing-home-18-june-2024.pdf", _WORSE,
     "Regulation 23(f): item=not_compliant appendix=substantially_compliant"),
    ("NH_2026_485-baltinglass-community-hospital-19-january-2026.pdf", _WORSE,
     "Regulation 7(3): item=not_compliant appendix=substantially_compliant"),
    ("NH_2023_184-tlc-centre-santry-6-october-2023.pdf", "corpus: one centre_id with different centre_names (info)",
     "OSV-0000184: ['TLC Centre Santry', 'The Residence Santry']"),
}


# ---------------------------------------------------------------- runner

def corpus_violations(reports: list[ParsedReport]) -> list[tuple[str, str, str]]:
    """(source_file, check, detail) for rules that compare reports with each other."""
    bad: list[tuple[str, str, str]] = []
    fieldwork_ids: dict[str, list[str]] = defaultdict(list)  # fieldwork_id -> [source_file, ...]
    centre_names: dict[str, dict[str, str]] = defaultdict(dict)  # centre_id -> {centre_name: first source_file}
    for r in reports:
        fieldwork_ids[r.cover.fieldwork_id].append(r.source_file)
        centre_names[r.cover.centre_id].setdefault(r.cover.centre_name, r.source_file)

    for fieldwork_id, files in fieldwork_ids.items():
        if len(files) > 1:
            bad.append((files[0], "corpus: fieldwork_id not unique", f"{fieldwork_id} in {len(files)} reports"))
    for cid, names in centre_names.items():
        if len(names) > 1:
            bad.append((next(iter(names.values())), "corpus: one centre_id with different centre_names (info)", f"{cid}: {sorted(names)}"))
    return bad


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else DEFAULT_JSONL
    use_pdf = "--no-pdf" not in sys.argv

    by_check: dict[str, list[tuple[str, str]]] = defaultdict(list)
    reports = load_reports(path)  # also enforces the enums: judgment, risk, date type
    n = len(reports)
    for r in reports:
        found = check_report(r) + (check_against_pdf(r) if use_pdf else [])
        for check, detail in found:
            by_check[check].append((r.source_file, detail))
    for source_file, check, detail in corpus_violations(reports):
        by_check[check].append((source_file, detail))

    print(f"{path.name}: {n} reports, {sum(len(v) for v in by_check.values())} violations in {len(by_check)} checks")
    for check, hits in sorted(by_check.items(), key=lambda kv: -len(kv[1])):
        reports = {name for name, _ in hits}
        print(f"\n[{len(hits):4}] {check}  ({len(reports)} reports)")
        for name, detail in hits[:5]:
            print(f"        {name[:60]:60} {detail}")
        if len(hits) > 5:
            print(f"        ... {len(hits) - 5} more")


if __name__ == "__main__":
    main()
