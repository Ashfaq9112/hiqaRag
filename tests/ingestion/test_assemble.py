from ingestion.assemble import repair_finding_titles
from ingestion.models import AppendixRow, Dimension, Judgment, RegulationFinding, RegulationSeries


def finding(number: str, title: str, text: str = "", judgment: Judgment = Judgment.COMPLIANT) -> RegulationFinding:
    return RegulationFinding(
        series=RegulationSeries.CARE,
        regulation_number=number,
        title=title,
        dimension=Dimension.QUALITY_AND_SAFETY,
        text=text,
        judgment=judgment,
    )


def appendix_row(number: str, title: str, judgment: Judgment = Judgment.COMPLIANT) -> AppendixRow:
    return AppendixRow(
        series=RegulationSeries.CARE,
        regulation_number=number,
        title=title,
        dimension=Dimension.QUALITY_AND_SAFETY,
        judgment=judgment,
    )


# Loughtown House, Regulation 9: the PDF text lost the capital "T", so the body line starts lowercase and the
# findings parser read it as the second line of a wrapped heading.
LOUGHTOWN_TITLE = "Residents' rights he rights of residents were upheld, and the privacy and dignity of residents was respected."


def test_body_swallowed_into_the_title_is_moved_back_to_the_text() -> None:
    repaired = repair_finding_titles([finding("9", LOUGHTOWN_TITLE)], [appendix_row("9", "Residents' rights")])
    assert repaired[0].title == "Residents' rights"
    assert repaired[0].text == "he rights of residents were upheld, and the privacy and dignity of residents was respected."
    assert repaired[0].judgment == Judgment.COMPLIANT


def test_elmville_title_with_a_multi_sentence_body() -> None:
    title = "Admissions and contract for the provision of services there were no planned admissions to the centre. This required review."
    repaired = repair_finding_titles(
        [finding("24", title, judgment=Judgment.SUBSTANTIALLY_COMPLIANT)],
        [appendix_row("24", "Admissions and contract for the provision of services", Judgment.SUBSTANTIALLY_COMPLIANT)],
    )
    assert repaired[0].title == "Admissions and contract for the provision of services"
    assert repaired[0].text == "there were no planned admissions to the centre. This required review."


def test_a_finding_whose_title_matches_the_appendix_is_unchanged() -> None:
    original = finding("15", "Staffing", text="There were enough staff on duty.")
    assert repair_finding_titles([original], [appendix_row("15", "Staffing")]) == [original]


def test_a_finding_that_has_text_is_never_touched() -> None:
    original = finding("15", "Staffing levels and rosters", text="There were enough staff on duty.")
    assert repair_finding_titles([original], [appendix_row("15", "Staffing")]) == [original]


def test_a_title_that_differs_from_the_appendix_but_does_not_start_with_it_is_left_alone() -> None:
    original = finding("15", "Workforce")
    assert repair_finding_titles([original], [appendix_row("15", "Staffing")]) == [original]


def test_a_finding_with_no_appendix_row_is_left_alone() -> None:
    original = finding("15", "Staffing")
    assert repair_finding_titles([original], []) == [original]
