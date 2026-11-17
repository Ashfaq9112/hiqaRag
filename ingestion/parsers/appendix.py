import re

from ingestion.models import AppendixRow, Dimension, Judgment, RegulationSeries
from ingestion.parsers.headings import (
    APPENDIX_HEADING,
    CAPACITY_HEADING,
    COMPLIANCE_PLAN_HEADING,
    QUALITY_HEADING,
)

# One table row: a regulation heading, then the title (which may wrap over several lines), then a line that is
# only the judgment ("Substantially \ncompliant" breaks inside the judgment, hence \s+). The title is
# matched lazily, so it stops at the first line that is just a judgment.
# A registration regulation can also be listed as "Registration Regulation 8 (1)" with no colon and no title.
_ROW = re.compile(
    r"^(?:(Registration )?Regulation (\d+):[ \t]*|(Registration )Regulation (\d+)[ \t]*\(\d+\)[ \t]*\n)(.*?)"
    r"^[ \t]*(Compliant|Substantially\s+compliant|Not\s+compliant)[ \t]*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def parse_appendix(text: str) -> list[AppendixRow]:
    """Appendix 1: every regulation considered, with its judgment, grouped under its dimension."""
    start = re.compile(APPENDIX_HEADING, re.MULTILINE).search(text)
    if start is None:
        raise ValueError("Appendix 1 heading not found")
    # The compliance plan repeats "Regulation N: title ... Judgment" in its own tables, so stop before it.
    plan = re.compile(COMPLIANCE_PLAN_HEADING, re.MULTILINE).search(text, start.end())
    appendix = text[start.end() : plan.start() if plan else len(text)]

    capacity = re.compile(CAPACITY_HEADING, re.MULTILINE).search(appendix)
    quality = re.compile(QUALITY_HEADING, re.MULTILINE).search(appendix)
    if capacity is None or quality is None:
        raise ValueError("dimension headings not found in Appendix 1")

    return [
        *_rows(appendix[capacity.end() : quality.start()], Dimension.CAPACITY_AND_CAPABILITY),
        *_rows(appendix[quality.end() :], Dimension.QUALITY_AND_SAFETY),
    ]


def _rows(region: str, dimension: Dimension) -> list[AppendixRow]:
    return [
        AppendixRow(
            series=RegulationSeries.REGISTRATION if m.group(1) or m.group(3) else RegulationSeries.CARE,
            regulation_number=m.group(2) or m.group(4),
            title=" ".join(m.group(5).split()),
            dimension=dimension,
            judgment=Judgment(m.group(6)),
        )
        for m in _ROW.finditer(region)
    ]
