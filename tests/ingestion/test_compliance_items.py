"""Compliance plan items (Section 2) on real reports: they are read from PDF tables, which text fixtures cannot imitate.

Each test goes through parse_report, the same path as production. Skipped when the PDF is not on this machine.
"""

from datetime import date
from functools import cache
from pathlib import Path

import pytest

from ingestion.assemble import parse_report
from ingestion.models import CompliancePlanItem, Judgment, RiskRating

PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "downloaded_reports"

pytestmark = pytest.mark.slow


@cache
def items(pdf_name: str) -> list[CompliancePlanItem]:
    matches = list(PDF_DIR.rglob(pdf_name))
    if not matches:
        pytest.skip(f"{pdf_name} not found under {PDF_DIR}")
    _, report = parse_report(matches[0])
    assert report is not None and report.compliance_plan is not None
    return report.compliance_plan.items


def refs(pdf_name: str) -> list[str]:
    return [i.regulation_ref for i in items(pdf_name)]


def test_st_dominics_baseline_rows_are_complete() -> None:
    rows = items("DIS_2023_1507-st-dominics-services-18-october-2023.pdf")
    assert len(rows) == 8
    first = rows[0]
    assert first.regulation_ref == "Regulation 15(1)"
    assert (first.judgment, first.risk_rating, first.due_date) == (Judgment.NOT_COMPLIANT, RiskRating.ORANGE, date(2023, 12, 1))
    assert all(i.risk_rating and i.due_date for i in rows)


def test_teach_michel_split_ref_is_joined_into_one_item() -> None:
    assert "Regulation 05(6)(c)" in refs("DIS_2023_5700-teach-michel-services-05-september-2023.pdf")


def test_arranmore_has_no_truncated_row_and_no_fake_row() -> None:
    pdf = "DIS_2026_3591-arranmore-21-january-2026.pdf"
    assert refs(pdf) == ["Regulation 24(3)", "Regulation 24(4)(a)", "Regulation 24(4)(b)", "Regulation 04(3)", "Regulation 07(4)"]
    # "Regulation 5(1)" appears inside this requirement's text; it must not become a row of its own
    reg_24_4_b = items(pdf)[2]
    assert reg_24_4_b.requirement.endswith("in accordance with Regulation 5(1) and the statement of purpose .")


def test_coolfin_several_rows_for_one_regulation_stay_separate() -> None:
    pdf = "DIS_2024_2375-coolfin-24-october-2024.pdf"
    assert len(items(pdf)) == 12
    assert [r for r in refs(pdf) if r.startswith("Regulation 23")] == ["Regulation 23(1)(a)", "Regulation 23(1)(c)", "Regulation 23(1)(d)"]


def test_peamount_row_without_a_risk_rating_gets_none() -> None:
    rows = {i.regulation_ref: i for i in items("DIS_2026_3505-peamount-healthcare-neurological-disability-service-22-january-2026.pdf")}
    assert len(rows) == 4
    assert rows["Regulation 23(2)(b)"].risk_rating is None
    assert rows["Regulation 23(2)(b)"].due_date == date(2026, 6, 11)
    assert all(i.risk_rating for ref, i in rows.items() if ref != "Regulation 23(2)(b)")


def test_aperee_camp_rows_without_dates_get_none() -> None:
    rows = items("NH_2023_5406-aperee-living-camp-1-august-2023.pdf")
    assert len(rows) == 12
    assert all(i.due_date is None for i in rows)
    assert all(i.risk_rating for i in rows)


def test_ratoath_refs_without_a_sub_bracket_are_kept() -> None:
    found = refs("NH_2024_152-ratoath-manor-nursing-home-14-august-2024.pdf")
    assert "Regulation 27" in found and "Regulation 23(c)" in found
