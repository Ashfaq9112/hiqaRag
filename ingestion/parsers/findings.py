import re

from ingestion.models import Dimension, Judgment, RegulationFinding, RegulationSeries
from ingestion.parsers.appendix import parse_appendix
from ingestion.parsers.headings import APPENDIX_HEADING, CAPACITY_HEADING, QUALITY_HEADING

# Where the first regulation block starts inside a dimension section: either straight after the section
# heading (no intro paragraph) or after a finished sentence. A prose mention of a regulation can wrap onto a
# line starting "Regulation N:", but then the previous line stops mid-sentence, so it is not matched.
_FIRST_BLOCK = re.compile(
    r"(?:\A\s*|(?<=[.!?])[ \t]*\n(?:[ \t]*\n)*)(?=(?:Registration )?Regulation \d+:)"
)

# Every regulation block ends with its judgment line; the casing and the line break inside the
# judgment ("Substantially \ncompliant") vary, Judgment._missing_ normalises them.
_JUDGMENT = re.compile(r"Judgment:\s*(Compliant|Substantially\s+compliant|Not\s+compliant)", re.IGNORECASE)

_HEADING = re.compile(r"(Registration )?Regulation (\d+):\s*(.*)")
# "Registration Regulation 8 (1)": no colon and no title
_BARE_REGISTRATION_HEADING = re.compile(r"(Registration )Regulation (\d+)[ \t]*\(\d+\)[ \t]*$")
# Any line that opens a regulation block, used to find the first block when the intro has no closing punctuation.
_ANY_HEADING = re.compile(
    r"^[ \t]*(?:(Registration )?Regulation (\d+):|(Registration )Regulation (\d+)[ \t]*\(\d+\)[ \t]*$)", re.MULTILINE
)


def parse_findings(text: str) -> list[RegulationFinding]:
    """One finding per regulation block, capacity and capability first, then quality and safety."""
    return [
        *_parse_dimension(text, Dimension.CAPACITY_AND_CAPABILITY, CAPACITY_HEADING, QUALITY_HEADING),
        *_parse_dimension(text, Dimension.QUALITY_AND_SAFETY, QUALITY_HEADING, APPENDIX_HEADING),
    ]


def _parse_dimension(text: str, dimension: Dimension, start: str, end: str) -> list[RegulationFinding]:
    s = re.compile(start, re.MULTILINE).search(text)
    if s is None:
        raise ValueError(f"{dimension} heading not found")
    e = re.compile(end, re.MULTILINE).search(text, s.end())
    if e is None:
        raise ValueError(f"heading after {dimension} not found")
    region = text[s.end() : e.start()]

    pos = first_block_start(text, region, dimension)
    if pos is None:  # a dimension with no regulation blocks
        return []

    findings: list[RegulationFinding] = []
    for j in _JUDGMENT.finditer(region, pos):
        findings.append(_parse_block(region[pos : j.start()], dimension, Judgment(j.group(1))))
        pos = j.end()
    return findings


def first_block_start(text: str, region: str, dimension: Dimension) -> int | None:
    """Offset in `region` where the first regulation block starts (the intro ends); None if there are no blocks.

    Shared with narrative.py so the intro and the findings always agree on where the intro stops.
    """
    first = _FIRST_BLOCK.search(region)
    return first.end() if first else _first_block_from_appendix(text, region, dimension)


def _first_block_from_appendix(text: str, region: str, dimension: Dimension) -> int | None:
    """Start of the first block when the sentence-end rule found none but the section has judgments.

    The intro can end without punctuation (or in a bullet), so its last line does not look finished. The Appendix
    lists the same regulations in the same order, so the first block is the last heading for its regulation
    before the first judgment; earlier ones are prose mentions that wrapped onto a line start.
    """
    judgment = _JUDGMENT.search(region)
    if judgment is None:
        return None
    try:
        first_row = next(row for row in parse_appendix(text) if row.dimension == dimension)
    except (ValueError, StopIteration):
        return None
    start = None
    for m in _ANY_HEADING.finditer(region, 0, judgment.start()):
        registration = m.group(1) or m.group(3)
        series = RegulationSeries.REGISTRATION if registration else RegulationSeries.CARE
        if (series, m.group(2) or m.group(4)) == (first_row.series, first_row.regulation_number):
            start = m.start()
    return start


def _parse_block(block: str, dimension: Dimension, judgment: Judgment) -> RegulationFinding:
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    heading = _HEADING.match(lines[0]) if lines else None
    bare = _BARE_REGISTRATION_HEADING.match(lines[0]) if lines else None
    if heading is not None:
        registration, number, title = heading.groups()
    elif bare is not None:
        registration, number, title = bare.group(1), bare.group(2), ""
    else:
        raise ValueError(f"regulation heading not found at: {block[:80]!r}")

    # A long title wraps onto the next line(s); body text always starts with an uppercase letter or digit.
    i = 1
    while title and i < len(lines) and lines[i][0].islower():
        title += " " + lines[i]
        i += 1

    return RegulationFinding(
        series=RegulationSeries.REGISTRATION if registration else RegulationSeries.CARE,
        regulation_number=number,
        title=title.strip(),
        dimension=dimension,
        text=" ".join(" ".join(lines[i:]).split()),
        judgment=judgment,
    )
