import pytest

from ingestion.models import Dimension, Judgment, RegulationSeries
from ingestion.parsers.appendix import parse_appendix
from ingestion.parsers.text import clean_text

PAGES = [
    "How we inspect \nA full list is in \nAppendix 1. \n",
    " \nPage 17 of 20 \n \nAppendix 1 - Full list of regulations considered under each dimension \n \n"
    "This inspection was carried out to assess compliance and the regulations considered were:   \n \n"
    " Regulation Title \nJudgment \nCapacity and capability \n \n"
    "Registration Regulation 7: Applications by registered \nproviders for the variation or removal of conditions of \n"
    "registration \nNot compliant \n"
    "Regulation 15: Staffing \nNot compliant \n"
    "Regulation 21: Records \nSubstantially \ncompliant \n",
    " \nPage 18 of 20 \n \nQuality and safety \n \n"
    "Regulation 5: Individual assessment and care plan \nCompliant \n"
    "Regulation 9: Residents' rights \nNot Compliant \n \n \n",
    " \nPage 19 of 20 \n \nCompliance Plan for Lystoll Lodge Nursing Home \n"
    "Regulation Heading \nJudgment \nRegistration Regulation 7: Applications \nby registered providers \n \n"
    "Not Compliant \n",
]
TEXT = clean_text(PAGES)


def test_parse_appendix_reads_rows_in_both_dimensions() -> None:
    rows = parse_appendix(TEXT)
    assert [(r.series, r.regulation_number, r.dimension, r.judgment) for r in rows] == [
        (RegulationSeries.REGISTRATION, "7", Dimension.CAPACITY_AND_CAPABILITY, Judgment.NOT_COMPLIANT),
        (RegulationSeries.CARE, "15", Dimension.CAPACITY_AND_CAPABILITY, Judgment.NOT_COMPLIANT),
        (RegulationSeries.CARE, "21", Dimension.CAPACITY_AND_CAPABILITY, Judgment.SUBSTANTIALLY_COMPLIANT),
        (RegulationSeries.CARE, "5", Dimension.QUALITY_AND_SAFETY, Judgment.COMPLIANT),
        (RegulationSeries.CARE, "9", Dimension.QUALITY_AND_SAFETY, Judgment.NOT_COMPLIANT),
    ]


def test_wrapped_title_is_joined_into_one_line() -> None:
    first = parse_appendix(TEXT)[0]
    assert first.title == "Applications by registered providers for the variation or removal of conditions of registration"


def test_compliance_plan_tables_are_not_read_as_appendix_rows() -> None:
    # the plan repeats "Registration Regulation 7 ... Not Compliant"; it must not add a second row
    assert len(parse_appendix(TEXT)) == 5


def test_report_without_compliance_plan() -> None:
    rows = parse_appendix(TEXT[: TEXT.index("Compliance Plan for")])
    assert len(rows) == 5


def test_missing_appendix_raises() -> None:
    with pytest.raises(ValueError, match="Appendix 1 heading not found"):
        parse_appendix("no appendix here")


def test_registration_row_without_colon_or_title() -> None:
    text = (
        "Appendix 1 - Full list of regulations considered under each dimension \n"
        "Capacity and capability \n \n"
        "Registration Regulation 8 (1) \nCompliant \n"
        "Regulation 15: Staffing \nNot compliant \n"
        "Quality and safety \n \n"
        "Regulation 5: Individual assessment and care plan \nCompliant \n"
    )
    rows = parse_appendix(text)
    assert [(r.series, r.regulation_number, r.title) for r in rows[:2]] == [
        (RegulationSeries.REGISTRATION, "8", ""),
        (RegulationSeries.CARE, "15", "Staffing"),
    ]
