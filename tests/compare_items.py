"""Compare compliance items: old parser (saved in reports_400.jsonl) vs new table extractor, as JSON.

uv run python tests/compare_items.py DIS_2023_1507-st-dominics-services-18-october-2023.pdf   # one report, prints the diff
uv run python tests/compare_items.py --all                                                    # every report, lists the ones that differ
Files are written to data/compare/<report>_old.json and <report>_new.json.
"""
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so "ingestion" is the project package, not tests/ingestion

import table_extractor  # noqa: E402
from ingestion.models import ParsedReport  # noqa: E402

OLD_JSONL = ROOT / "data/parsed/reports_400.jsonl"
OUT = ROOT / "data/compare"
_REF = re.compile(r"(Registration\s+)?Regulation\s*(\d+)((?:\s*\([^)]*\))*)")


def old_items() -> dict[str, list[dict]]:
    """source_file -> the old parser's compliance items as plain dicts."""
    items = {}
    with open(OLD_JSONL, encoding="utf-8") as f:
        for line in f:
            report = ParsedReport.model_validate_json(line)
            if report.compliance_plan:
                items[report.source_file] = [i.model_dump(mode="json") for i in report.compliance_plan.items]
    return items


def new_item(row: dict) -> dict:
    """A table row in the same shape as CompliancePlanItem.model_dump(mode='json'); null where the PDF has no risk or date."""
    m = _REF.fullmatch(row["ref"])
    registration, number, sub_refs = m.groups() if m else (None, None, "")
    d = row["date"]
    return {
        "regulation_ref": f"{'Registration ' if registration else ''}Regulation {number}{''.join(sub_refs.split())}" if m else row["ref"],
        "series": "registration" if registration else "care",
        "regulation_number": str(int(number)) if number else None,
        "requirement": row["requirement"],
        "judgment": row["judgment"].lower().replace(" ", "_"),
        "risk_rating": row["risk"].lower() if row["risk"] else None,
        "due_date": f"{d[6:]}-{d[3:5]}-{d[:2]}" if d else None,
    }


def compare(name: str, old: list[dict]) -> list[str]:
    new = [new_item(r) for r in table_extractor.table_rows(name)]
    OUT.mkdir(parents=True, exist_ok=True)
    texts = []
    for label, items in (("old", old), ("new", new)):
        text = json.dumps(items, indent=2, ensure_ascii=False)
        (OUT / f"{Path(name).stem}_{label}.json").write_text(text, encoding="utf-8")
        texts.append(text.splitlines())
    return list(difflib.unified_diff(texts[0], texts[1], "old", "new", lineterm="", n=2))


if __name__ == "__main__":
    old = old_items()
    if "--all" in sys.argv:
        differing = [name for name in old if compare(name, old[name])]
        print(f"{len(differing)} of {len(old)} reports differ")
        for name in differing:
            print("  ", name)
    else:
        name = sys.argv[1]
        print("\n".join(compare(name, old[name])) or "no differences")
