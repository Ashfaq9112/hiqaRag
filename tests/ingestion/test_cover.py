from datetime import date

import pytest

from ingestion.classifier import ReportKind
from ingestion.models import InspectionType, ServiceType
from ingestion.parsers.cover import parse_cover

NURSING_COVER = (
    " \nPage 1 of 25 \n \nReport of an inspection of a \nDesignated Centre for Older People. \n \n"
    "Issued by the Chief Inspector \n \nName of designated \ncentre: \nBelmont House Private Nursing \nHome \n"
    "Name of provider: \nBelmont Care Limited \nAddress of centre: \nGalloping Green, Stillorgan,  \nCo. Dublin \n"
    " \n \nType of inspection: \nUnannounced \nDate of inspection: \n \n30 July 2024 \n"
    "Centre ID: \nOSV-0000014 \nFieldwork ID: \nMON-0043166 \n"
)

CHILDREN_COVER = (
    " \nPage 1 of 21 \n \nReport of an inspection of a \nDesignated Centre for Disabilities \n(Children). \n \n"
    "Issued by the Chief Inspector \n \nName of designated \ncentre: \nHaughton House \n"
    "Name of provider: \nSt Catherine's Association CLG \nAddress of centre: \nWicklow  \n \n \n \n"
    "Type of inspection: \nAnnounced \nDate of inspection: \n \n10 September 2025 \n"
    "Centre ID: \nOSV-0001850 \nFieldwork ID: \nMON-0039335 \n"
)


def test_parse_cover_nursing_home() -> None:
    cover = parse_cover(NURSING_COVER, ReportKind.NURSING_HOME)
    assert cover.centre_name == "Belmont House Private Nursing Home"  # wrapped value joined
    assert cover.provider == "Belmont Care Limited"
    assert cover.address == "Galloping Green, Stillorgan, Co. Dublin"
    assert cover.inspection_type == InspectionType.UNANNOUNCED
    assert cover.inspection_date == date(2024, 7, 30)
    assert cover.centre_id == "OSV-0000014"
    assert cover.fieldwork_id == "MON-0043166"
    assert cover.service_type == ServiceType.NURSING_HOME


def test_parse_cover_disability_children() -> None:
    cover = parse_cover(CHILDREN_COVER, ReportKind.DISABILITY_CHILDREN)
    assert cover.inspection_type == InspectionType.ANNOUNCED
    assert cover.inspection_date == date(2025, 9, 10)
    assert cover.service_type == ServiceType.DISABILITY_CHILDREN


def test_parse_cover_disability_mixed() -> None:
    cover = parse_cover(CHILDREN_COVER.replace("(Children)", "(Mixed)"), ReportKind.DISABILITY_MIXED)
    assert cover.service_type == ServiceType.DISABILITY_MIXED


def test_parse_cover_short_notice_announced() -> None:
    cover = parse_cover(NURSING_COVER.replace("Unannounced", "Short Notice \nAnnounced"), ReportKind.NURSING_HOME)
    assert cover.inspection_type == InspectionType.SHORT_NOTICE_ANNOUNCED


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("22 & 29 May 2024", date(2024, 5, 22)),
        ("07 and 08 February 2024", date(2024, 2, 7)),
        ("11 and 12 December 2023", date(2023, 12, 11)),
        ("30 June and 1 July 2024", date(2024, 6, 30)),  # a range can cross a month
    ],
)
def test_parse_cover_multi_day_inspection_uses_first_day(written: str, expected: date) -> None:
    cover = parse_cover(NURSING_COVER.replace("30 July 2024", written), ReportKind.NURSING_HOME)
    assert cover.inspection_date == expected


def test_parse_cover_missing_label_raises() -> None:
    with pytest.raises(ValueError, match="cover labels not found"):
        parse_cover("Name of designated centre: X", ReportKind.NURSING_HOME)


@pytest.mark.parametrize("kind", [ReportKind.THEMATIC, ReportKind.UNKNOWN])
def test_parse_cover_rejects_non_service_kinds(kind: ReportKind) -> None:
    with pytest.raises(ValueError):
        parse_cover(NURSING_COVER, kind)
