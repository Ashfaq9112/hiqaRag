"""Section 1 (provider responses) and the no-plan / no-Section-2 edges, on text fixtures.

Section 2 (items) is read from PDF tables, so it is tested on real reports in test_compliance_items.py.
"""

import re

import pytest

from ingestion.models import Judgment, RegulationSeries
from ingestion.parsers.compliance_plan import _parse_responses, parse_compliance_plan
from ingestion.parsers.headings import COMPLIANCE_PLAN_HEADING
from ingestion.parsers.text import clean_text

PAGES = [
    "Appendix 1 - Full list of regulations \nQuality and safety \nRegulation 5: Individual plan \nCompliant \n",
    " \nPage 18 of 20 \n \nCompliance Plan for Lystoll Lodge Nursing Home \nOSV-0000246  \n \n"
    "Section 1 is the compliance plan. \nSection 2 is the list of all regulations. \n \n"
    "Compliance plan provider’s response: \n \nRegulation Heading \nJudgment \n"
    "Registration Regulation 7: Applications \nby registered providers for the \nvariation or removal of conditions of \n"
    "registration \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Registration Regulation 7: \n"
    "Applications by registered providers for the variation or removal of conditions of \nregistration: \n"
    "We are awaiting documentation from our engineer. \n"
    "Regulation 23: Governance and \nmanagement \n \nSubstantially Compliant \n"
    "Outline how you are going to come into compliance with Regulation 23: Governance and \nmanagement: \n"
    "A new PIC has been recruited. \nThe audit schedule is implemented. \n"
    "Regulation 17: Premises \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Regulation 17: Premises: \n"
    "The shelving will be fitted. \n \n \n",
    " \nPage 19 of 20 \n \nSection 2:  \n \nRegulations to be complied with \n \n",
]
TEXT = clean_text(PAGES)


def section_1(text: str) -> str:
    """The text between the 'Compliance Plan for' heading and 'Section 2:', which is what parse_compliance_plan hands to _parse_responses."""
    plan = re.compile(COMPLIANCE_PLAN_HEADING, re.MULTILINE).search(text)
    section_2 = re.compile(r"^Section 2:[ \t]*$", re.MULTILINE).search(text)
    assert plan is not None and section_2 is not None
    return text[plan.end() : section_2.start()]


def test_no_compliance_plan_returns_none() -> None:
    # returns before the PDF is touched, so no document is needed
    assert parse_compliance_plan(TEXT[: TEXT.index("Compliance Plan for")], None) is None  # type: ignore[arg-type]


def test_plan_without_section_2_raises() -> None:
    with pytest.raises(ValueError, match="Section 2"):
        parse_compliance_plan("Compliance Plan for X \nno sections", None)  # type: ignore[arg-type]


def test_responses_one_per_regulation_with_judgment_and_series() -> None:
    responses = _parse_responses(section_1(TEXT))
    assert [(r.series, r.regulation_number, r.judgment) for r in responses] == [
        (RegulationSeries.REGISTRATION, "7", Judgment.NOT_COMPLIANT),
        (RegulationSeries.CARE, "23", Judgment.SUBSTANTIALLY_COMPLIANT),
        (RegulationSeries.CARE, "17", Judgment.NOT_COMPLIANT),
    ]


def test_response_text_drops_the_repeated_heading_sentence() -> None:
    responses = _parse_responses(section_1(TEXT))
    reg23, reg17 = responses[1], responses[2]
    assert reg23.title == "Governance and management"  # wrapped heading joined
    assert reg23.response_text == "A new PIC has been recruited. The audit schedule is implemented."
    assert reg17.response_text == "The shelving will be fitted."  # stops at Section 2, not at the intro "Section 2 is..."


def test_outline_sentence_never_leaks_into_response_text() -> None:
    for response in _parse_responses(section_1(TEXT)):
        assert "Outline how" not in response.response_text


# A heading block printed twice in a row: the first copy has no response text.
DUPLICATED_BLOCK = (
    "Regulation 17: Premises \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Regulation 17: Premises: \n"
    "Regulation 17: Premises \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Regulation 17: Premises: \n"
    "The shelving will be fitted. \n"
)


def test_duplicated_heading_block_gives_one_response() -> None:
    responses = _parse_responses(DUPLICATED_BLOCK)
    assert len(responses) == 1
    assert responses[0].response_text == "The shelving will be fitted."


# A response body that itself contains a line starting "Regulation 12:" must not be taken as the next block's heading.
BODY_LINE_LOOKS_LIKE_HEADING = (
    "Regulation 23: Governance and management \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Regulation 23: Governance and management: \n"
    "We will review the audits. \nRegulation 12: Personal possessions will be reviewed monthly. \n"
    "Regulation 17: Premises \n \nSubstantially Compliant \n"
    "Outline how you are going to come into compliance with Regulation 17: Premises: \n"
    "The shelving will be fitted. \n"
)


def test_body_line_starting_with_regulation_is_not_taken_as_the_next_heading() -> None:
    first, second = _parse_responses(BODY_LINE_LOOKS_LIKE_HEADING)
    assert (second.regulation_number, second.title, second.judgment) == (
        "17",
        "Premises",
        Judgment.SUBSTANTIALLY_COMPLIANT,
    )
    assert second.response_text == "The shelving will be fitted."
    assert (first.regulation_number, first.judgment) == ("23", Judgment.NOT_COMPLIANT)
    assert "Regulation 12: Personal possessions will be reviewed monthly." in first.response_text


# Registration Regulation 6 and Regulation 6 are different regulations: the same number must not be mistaken for a duplicate.
SAME_NUMBER_TWO_SERIES = (
    "Registration Regulation 6: Changes to information supplied \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Registration Regulation 6: Changes to information supplied: \n"
    "The form will be sent. \n"
    "Regulation 6: Healthcare \n \nNot Compliant \n"
    "Outline how you are going to come into compliance with Regulation 6: Healthcare: \n"
    "A GP review is arranged. \n"
)


def test_same_number_in_two_series_stays_two_responses() -> None:
    responses = _parse_responses(SAME_NUMBER_TWO_SERIES)
    assert [(r.series, r.regulation_number, r.response_text) for r in responses] == [
        (RegulationSeries.REGISTRATION, "6", "The form will be sent."),
        (RegulationSeries.CARE, "6", "A GP review is arranged."),
    ]
