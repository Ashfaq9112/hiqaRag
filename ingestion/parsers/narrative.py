import re

from ingestion.models import Dimension, Narrative
from ingestion.parsers.findings import first_block_start
from ingestion.parsers.headings import APPENDIX_HEADING, CAPACITY_HEADING, QUALITY_HEADING

ABOUT_BOILERPLATE = (
    "The following information has been submitted by the registered provider and describes the service they provide."
)

_RESIDENTS = re.compile(r"Number of residents on the\s+date of inspection:\s*(\d+)")


def _section(text: str, start: str, end: str) -> str | None:
    """Text between a heading line and the next end marker, whitespace collapsed; None if either is missing."""
    s = re.compile(start, re.MULTILINE).search(text)
    if s is None:
        return None
    e = re.compile(end, re.MULTILINE).search(text, s.end())
    if e is None:
        return None
    return " ".join(text[s.end() : e.start()].split()) or None


def _intro(text: str, start: str, end: str, dimension: Dimension) -> str | None:
    """Narrative between a dimension heading and its first regulation block (whole section if it has no blocks)."""
    s = re.compile(start, re.MULTILINE).search(text)
    if s is None:
        return None
    e = re.compile(end, re.MULTILINE).search(text, s.end())
    if e is None:
        return None
    region = text[s.end() : e.start()]
    cut = first_block_start(text, region, dimension)
    if cut is not None:
        region = region[:cut]
    return " ".join(region.split()) or None


def parse_about_centre(text: str) -> str:
    about = _section(
        text,
        start=r"^About the designated centre[ \t]*$",
        end=r"^The following information outlines some additional data",
    )
    if about is None:
        raise ValueError("'About the designated centre' section not found")
    return about.removeprefix(ABOUT_BOILERPLATE).strip()


def parse_residents(text: str) -> int | None:
    m = _RESIDENTS.search(text)
    return int(m.group(1)) if m else None


def parse_narrative(text: str) -> Narrative:
    return Narrative(
        how_we_inspect=_section(
            text,
            start=r"^How we inspect[ \t]*$",
            end=r"^This inspection was carried out during",  # inspector times table follows; not extracted
        ),
        what_residents_told_us=_section(
            text,
            start=r"^What residents told us and what inspectors observed[ \t]*$",
            end=CAPACITY_HEADING,
        ),
        capacity_intro=_intro(text, CAPACITY_HEADING, QUALITY_HEADING, Dimension.CAPACITY_AND_CAPABILITY),
        quality_intro=_intro(text, QUALITY_HEADING, APPENDIX_HEADING, Dimension.QUALITY_AND_SAFETY),
    )
