"""End to end: parse_report on whole real reports, checking that the parsers are wired together correctly.

The unit tests prove each parser alone; these prove assemble.py hands them the right input and keeps every field.
Skipped when the PDF is not on this machine.
"""

from datetime import date
from functools import cache
from pathlib import Path

import pytest

from ingestion.assemble import parse_report
from ingestion.classifier import ReportKind
from ingestion.models import InspectionType, ParsedReport, ServiceType

PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "downloaded_reports"

pytestmark = pytest.mark.slow


@cache
def parse(pdf_name: str) -> tuple[ReportKind, ParsedReport | None]:
    matches = list(PDF_DIR.rglob(pdf_name))
    if not matches:
        pytest.skip(f"{pdf_name} not found under {PDF_DIR}")
    return parse_report(matches[0])


def assert_findings_agree_with_appendix(report: ParsedReport) -> None:
    """Each finding's judgment is the one the Appendix 1 table gives for the same regulation (series + number)."""
    appendix = {(row.series, row.regulation_number): row.judgment for row in report.appendix}
    findings = {(f.series, f.regulation_number): f.judgment for f in report.findings}
    assert len(report.findings) == len(findings)  # no regulation found twice
    assert findings == appendix


def test_st_dominics_with_a_compliance_plan() -> None:
    kind, report = parse("DIS_2023_1507-st-dominics-services-18-october-2023.pdf")
    assert kind == ReportKind.DISABILITY_ADULTS and report is not None

    cover = report.cover  # classifier + cover, read from page 1
    assert (cover.centre_name, cover.provider) == ("St Dominic's Services", "Ability West")
    assert (cover.centre_id, cover.fieldwork_id) == ("OSV-0001507", "MON-0041321")
    assert cover.service_type == ServiceType.DISABILITY_ADULTS
    assert cover.inspection_type == InspectionType.UNANNOUNCED
    assert cover.inspection_date == date(2023, 10, 18)

    assert report.about_centre and report.residents_on_date == 6
    assert report.narrative.what_residents_told_us and report.narrative.capacity_intro and report.narrative.quality_intro

    assert (len(report.findings), len(report.appendix)) == (12, 12)
    assert_findings_agree_with_appendix(report)

    plan = report.compliance_plan
    assert plan is not None
    assert (len(plan.responses), len(plan.items)) == (6, 8)
    responses = {(r.series, r.regulation_number) for r in plan.responses}
    assert all((item.series, item.regulation_number) in responses for item in plan.items)  # items link to responses

    assert report.parse_warnings == []


def test_report_with_every_regulation_compliant_has_no_plan() -> None:
    kind, report = parse("NH_2024_355-little-flower-nursing-home-21-february-2024.pdf")
    assert kind == ReportKind.NURSING_HOME and report is not None
    assert (report.cover.centre_name, report.cover.fieldwork_id) == ("Little Flower Nursing Home", "MON-0042751")
    assert report.cover.service_type == ServiceType.NURSING_HOME
    assert (len(report.findings), len(report.appendix), report.residents_on_date) == (20, 20, 50)
    assert_findings_agree_with_appendix(report)
    assert report.compliance_plan is None  # valid data, not an error
    assert report.parse_warnings == []


def test_thematic_inspection_is_skipped() -> None:
    kind, report = parse("DIS_2023_2347-sarto-rise-22-november-2023.pdf")
    assert kind == ReportKind.THEMATIC
    assert report is None
