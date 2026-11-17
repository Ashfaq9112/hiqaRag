import pytest

from ingestion.models import Dimension, Judgment, RegulationSeries
from ingestion.parsers.findings import parse_findings
from ingestion.parsers.text import clean_text

PAGES = [
    "How we inspect \nA full list is in \nAppendix 1. \n",
    " \nPage 6 of 9 \n \nCapacity and capability \n \n"
    "Overall, governance was good. This is discussed under \nRegulation 23: Governance and management \nlater on. \n"
    "Registration Regulation 5: Application for registration or renewal of \nregistration \n"
    "The prescribed documentation had been submitted. \n \n \nJudgment: Compliant \n"
    "Regulation 15: Staffing \nThere were enough staff on duty. \n \n \nJudgment: Not compliant \n",
    " \nPage 7 of 9 \n \nRegulation 34: Complaints procedure \n\n \nA complaints policy was in place. \n"
    "Judgment: Substantially \ncompliant \n"
    "Quality and safety \n \n"
    "Residents received a good standard of care. \n"
    "Regulation 5: Individual assessment and care plan \nCare plans were reviewed. \n \nJudgment: Compliant \n",
    " \nPage 8 of 9 \n \nAppendix 1 - Full list of regulations considered under each dimension \n"
    "Regulation 15: Staffing \nNot compliant \n",
]
TEXT = clean_text(PAGES)


def test_parse_findings_reads_every_block_in_both_dimensions() -> None:
    findings = parse_findings(TEXT)
    assert [(f.series, f.regulation_number, f.dimension) for f in findings] == [
        (RegulationSeries.REGISTRATION, "5", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.CARE, "15", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.CARE, "34", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.CARE, "5", Dimension.QUALITY_AND_SAFETY),
    ]


def test_wrapped_registration_title_is_joined_and_kept_apart_from_regulation_5() -> None:
    reg = parse_findings(TEXT)[0]
    assert (reg.series, reg.regulation_number) == (RegulationSeries.REGISTRATION, "5")
    assert reg.title == "Application for registration or renewal of registration"
    assert reg.text == "The prescribed documentation had been submitted."


def test_mid_sentence_regulation_mention_is_not_a_block() -> None:
    first = parse_findings(TEXT)[0]  # the intro mentions "Regulation 23: ..." on a line start but is not a block
    assert first.regulation_number != "23"


def test_judgments_are_normalised_including_a_line_break_inside_the_judgment() -> None:
    assert [f.judgment for f in parse_findings(TEXT)] == [
        Judgment.COMPLIANT,
        Judgment.NOT_COMPLIANT,
        Judgment.SUBSTANTIALLY_COMPLIANT,
        Judgment.COMPLIANT,
    ]


def test_heading_after_a_page_break_has_its_body_text() -> None:
    reg34 = parse_findings(TEXT)[2]
    assert reg34.title == "Complaints procedure"
    assert reg34.text == "A complaints policy was in place."


def test_block_text_excludes_the_judgment_line_and_the_next_heading() -> None:
    reg15 = parse_findings(TEXT)[1]
    assert reg15.text == "There were enough staff on duty."


def test_missing_dimension_heading_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        parse_findings("no sections here")


# An intro that does not end in punctuation (so the first heading is not recognised as one), and a
# "Registration Regulation 8 (1)" heading with no colon and no title.
UNPUNCTUATED_PAGES = [
    "Capacity and capability \n \nOverall governance was good and residents were safe in their home \n"
    "Registration Regulation 5: Application for registration or renewal of \nregistration \n"
    "Submitted. \n \nJudgment: Compliant \n"
    "Registration Regulation 8 (1) \nSince the last inspection an application was made. \n \nJudgment: Compliant \n"
    "Regulation 15: Staffing \nEnough staff. \n \nJudgment: Not compliant \n"
    "Quality and safety \n \nResidents were well supported and safe \n"
    "Regulation 5: Individual assessment and care plan \nCare plans were reviewed. \n \nJudgment: Compliant \n",
    "Appendix 1 - Full list of regulations considered under each dimension \nRegulation Title \nJudgment \n"
    "Capacity and capability \n \n"
    "Registration Regulation 5: Application for registration or \nrenewal of registration \nCompliant \n"
    "Registration Regulation 8 (1) \nCompliant \n"
    "Regulation 15: Staffing \nNot compliant \n"
    "Quality and safety \n \nRegulation 5: Individual assessment and care plan \nCompliant \n",
]
UNPUNCTUATED = clean_text(UNPUNCTUATED_PAGES)


def test_first_block_is_found_when_the_intro_has_no_closing_punctuation() -> None:
    findings = parse_findings(UNPUNCTUATED)
    assert [(f.series, f.regulation_number, f.dimension) for f in findings] == [
        (RegulationSeries.REGISTRATION, "5", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.REGISTRATION, "8", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.CARE, "15", Dimension.CAPACITY_AND_CAPABILITY),
        (RegulationSeries.CARE, "5", Dimension.QUALITY_AND_SAFETY),
    ]


def test_registration_heading_without_colon_or_title() -> None:
    reg8 = parse_findings(UNPUNCTUATED)[1]
    assert reg8.title == ""
    assert reg8.text == "Since the last inspection an application was made."
    assert reg8.judgment == Judgment.COMPLIANT
