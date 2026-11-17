import pytest

from ingestion.parsers.narrative import parse_about_centre, parse_narrative, parse_residents
from ingestion.parsers.text import clean_text

PAGES = [
    " \nPage 1 of 5 \nReport of an inspection of a \nDesignated Centre for Older People. \n",
    " \nPage 2 of 5 \n \nAbout the designated centre \n \n"
    "The following information has been submitted by the registered provider and \ndescribes the service they provide. \n \n"
    "Belmont House is a 156-bed centre providing care \nto residents. \n \n \n"
    "The following information outlines some additional data on this centre. \n \n \n"
    "Number of residents on the \ndate of inspection: \n140 \n",
    " \nPage 3 of 5 \n \nHow we inspect \n \nThis inspection was carried out to assess compliance. \n"
    "As part of our inspection, we: \n speak with residents, \n talk with staff. \n"
    "In order to summarise, we group the regulations under two dimensions of: \n \n"
    "1. Capacity and capability of the service: \nThis section describes leadership. \n \n"
    "2. Quality and safety of the service:  \nThis section describes care. \n",
    " \nPage 4 of 5 \n \nThis inspection was carried out during the following times:  \n \nDate \nInspector \nRole \n",
    " \nPage 5 of 5 \n \nWhat residents told us and what inspectors observed \n \n"
    "Residents were happy living in the centre. \n"
    "Staff were kind and respectful. \n \n"
    "Capacity and capability \n \n"
    "Overall, governance was good. This is discussed under \nRegulation 23: Governance and management \nlater on. \n"
    "Registration Regulation 5: Application for registration or renewal of \nregistration \n"
    "The prescribed documentation had been submitted. \n \nJudgment: Compliant \n"
    "Quality and safety \n \n"
    "Residents received a good standard of care. \nRegulation 12: Personal possessions \n"
    "Residents had adequate space. \n \nJudgment: Compliant \n"
    "Appendix 1 - Full list of regulations considered under each dimension \n",
]
TEXT = clean_text(PAGES)


def test_clean_text_drops_page_headers_and_normalises_bullets() -> None:
    assert "Page 2 of 5" not in TEXT
    assert "" not in TEXT
    assert "• speak with residents," in TEXT


def test_parse_about_centre_drops_boilerplate_and_stops_at_additional_data() -> None:
    assert parse_about_centre(TEXT) == "Belmont House is a 156-bed centre providing care to residents."


def test_parse_about_centre_missing_raises() -> None:
    with pytest.raises(ValueError):
        parse_about_centre("nothing here")


def test_parse_residents() -> None:
    assert parse_residents(TEXT) == 140
    assert parse_residents("no table") is None


def test_parse_narrative_sections() -> None:
    n = parse_narrative(TEXT)
    assert n.how_we_inspect is not None
    assert n.how_we_inspect.startswith("This inspection was carried out to assess compliance.")
    assert n.how_we_inspect.endswith("This section describes care.")  # stops before the inspector times table
    assert n.what_residents_told_us == "Residents were happy living in the centre. Staff were kind and respectful."


def test_narrative_intros_stop_at_first_real_regulation_heading() -> None:
    n = parse_narrative(TEXT)
    # the mid-sentence "Regulation 23: ..." wrap is prose; "Registration Regulation 5:" ends the intro
    assert n.capacity_intro == (
        "Overall, governance was good. This is discussed under Regulation 23: Governance and management later on."
    )
    assert n.quality_intro == "Residents received a good standard of care."


# Intros whose last sentence has no closing punctuation (Rosenheim-style), so the sentence-end rule finds nothing.
UNPUNCTUATED = clean_text(
    [
        "Capacity and capability \n \nOverall governance was good and residents were safe in their home \n"
        "Regulation 15: Staffing \nEnough staff. \n \nJudgment: Compliant \n"
        "Quality and safety \n \nResidents were well supported and safe \n"
        "Regulation 5: Individual assessment and care plan \nCare plans were reviewed. \n \nJudgment: Compliant \n",
        "Appendix 1 - Full list of regulations considered under each dimension \nRegulation Title \nJudgment \n"
        "Capacity and capability \n \nRegulation 15: Staffing \nCompliant \n"
        "Quality and safety \n \nRegulation 5: Individual assessment and care plan \nCompliant \n",
    ]
)


def test_narrative_intros_do_not_swallow_findings_when_intro_has_no_punctuation() -> None:
    n = parse_narrative(UNPUNCTUATED)
    assert n.capacity_intro == "Overall governance was good and residents were safe in their home"
    assert n.quality_intro == "Residents were well supported and safe"


def test_parse_narrative_missing_sections_are_none() -> None:
    n = parse_narrative("no sections here")
    assert n.model_dump() == {
        "how_we_inspect": None,
        "what_residents_told_us": None,
        "capacity_intro": None,
        "quality_intro": None,
    }
