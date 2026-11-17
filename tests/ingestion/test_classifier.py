import pytest

from ingestion.classifier import ReportKind, classify_report


@pytest.mark.parametrize(
    ("cover_text", "expected"),
    [
        ("Report of an Inspection of a\nDesignated Centre for Older People", ReportKind.NURSING_HOME),
        ("Report of an Inspection of a\nDesignated Centre for Disabilities (Adults)", ReportKind.DISABILITY_ADULTS),
        ("Report of an Inspection of a\nDesignated Centre for Disabilities (Children)", ReportKind.DISABILITY_CHILDREN),
        ("Report of an inspection of a\nDesignated Centre for Disabilities (Mixed).", ReportKind.DISABILITY_MIXED),
        (
            "Report of a Restrictive Practice Thematic Inspection of a\nDesignated Centre for Older People",
            ReportKind.THEMATIC,
        ),
        ("Designated Centre for\nOlder\nPeople", ReportKind.NURSING_HOME),
        ("Designated Centre for Disabilities", ReportKind.UNKNOWN),
        ("Report of an Inspection of a Hospital", ReportKind.UNKNOWN),
        ("", ReportKind.UNKNOWN),
    ],
)
def test_classify_report(cover_text: str, expected: ReportKind) -> None:
    assert classify_report(cover_text) == expected
