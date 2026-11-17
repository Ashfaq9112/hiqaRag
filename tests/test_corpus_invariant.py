import pytest

from tests.corpus_invariants import (
    DEFAULT_JSONL,
    KNOWN_EXCEPTIONS,
    PDF_DIR,
    check_against_pdf,
    check_report,
    corpus_violations,
    load_reports,
)

REPORTS = load_reports(DEFAULT_JSONL)  # runs once, when pytest imports this file


@pytest.mark.parametrize("report", REPORTS, ids=lambda r: r.source_file)
def test_report_has_no_new_violations(report):
    new = [
        (check, detail)
        for check, detail in check_report(report)
        if (report.source_file, check, detail) not in KNOWN_EXCEPTIONS
    ]
    assert new == []


def test_corpus_has_no_new_violations():
    new = [v for v in corpus_violations(REPORTS) if v not in KNOWN_EXCEPTIONS]
    assert new == []


@pytest.mark.slow
@pytest.mark.parametrize("report", REPORTS, ids=lambda r: r.source_file)
def test_report_matches_its_pdf(report):
    if not (PDF_DIR / report.source_file).exists():
        pytest.skip(f"PDF not on disk: {report.source_file}")
    new = [
        (check, detail)
        for check, detail in check_against_pdf(report)
        if (report.source_file, check, detail) not in KNOWN_EXCEPTIONS
    ]
    assert new == []


def test_known_exceptions_are_still_real():
    """Every accepted exception must still occur (Group A + corpus level), or it is dead weight."""
    seen = {(r.source_file, check, detail) for r in REPORTS for check, detail in check_report(r)}
    seen |= set(corpus_violations(REPORTS))
    assert KNOWN_EXCEPTIONS <= seen
