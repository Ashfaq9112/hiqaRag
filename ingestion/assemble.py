from pathlib import Path

import pymupdf

from ingestion.classifier import ReportKind, classify_report
from ingestion.models import AppendixRow, ParsedReport, RegulationFinding
from ingestion.parsers.appendix import parse_appendix
from ingestion.parsers.compliance_plan import parse_compliance_plan
from ingestion.parsers.cover import parse_cover
from ingestion.parsers.findings import parse_findings
from ingestion.parsers.narrative import parse_about_centre, parse_narrative, parse_residents
from ingestion.parsers.text import clean_text

SKIPPED_KINDS = (ReportKind.THEMATIC, ReportKind.UNKNOWN)


def repair_finding_titles(findings: list[RegulationFinding], appendix: list[AppendixRow]) -> list[RegulationFinding]:
    """Give back the body that the findings parser merged into a heading.

    When the PDF text layer drops the first capital of the body, that line starts lowercase and is read as the second
    line of a wrapped heading, so the title holds the whole body and `text` is empty. The Appendix is parsed
    separately and holds the clean title: if a finding with empty text has a title that starts with its Appendix
    title, split it there. Any other finding is returned unchanged.
    """
    appendix_titles = {(row.series, row.regulation_number): row.title for row in appendix}
    repaired = []
    for finding in findings:
        clean_title = appendix_titles.get((finding.series, finding.regulation_number))
        if clean_title and not finding.text.strip() and len(finding.title) > len(clean_title) and finding.title.startswith(clean_title):
            finding = finding.model_copy(update={"title": clean_title, "text": finding.title[len(clean_title):].strip()})
        repaired.append(finding)
    return repaired


def parse_report(pdf_path: Path, source_file: str | None = None) -> tuple[ReportKind, ParsedReport | None]:
    """Parse one inspection PDF. The report is None for thematic/unknown kinds; raises if a required part is missing."""
    with pymupdf.open(pdf_path) as doc:
        pages = [page.get_text() for page in doc]

        cover_text = clean_text(pages[:1])
        kind = classify_report(cover_text)
        if kind in SKIPPED_KINDS:
            return kind, None

        text = clean_text(pages)
        warnings: list[str] = []

        # the cover only reads page 1: its Fieldwork ID pattern runs to the end of whatever it is given
        cover = parse_cover(cover_text, kind)
        about_centre = parse_about_centre(text)
        findings = parse_findings(text)
        appendix = parse_appendix(text)

        try:
            residents = parse_residents(text)
        except ValueError as error:
            residents = None
            warnings.append(f"residents: {error}")

        report = ParsedReport(
            source_file=source_file or pdf_path.name,
            cover=cover,
            about_centre=about_centre,
            residents_on_date=residents,
            narrative=parse_narrative(text),
            findings=repair_finding_titles(findings, appendix),
            appendix=appendix,
            compliance_plan=parse_compliance_plan(text, doc),
            parse_warnings=warnings,
        )
        return kind, report
