
import re
from datetime import date, datetime

from ingestion.classifier import ReportKind
from ingestion.models import Cover, ServiceType

# Labels always appear in this order, so each value is the text up to the next label.
PATTERN = re.compile(
    r"Name of designated centre:(.*?)"
    r"Name of provider:(.*?)"
    r"Address of centre:(.*?)"
    r"Type of inspection:(.*?)"
    r"Date of inspection:(.*?)"
    r"Centre ID:(.*?)"
    r"Fieldwork ID:(.*)"
)

_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
# "30 July 2024", "22 & 29 May 2024", "07 and 08 February 2024", "30 June and 1 July 2024": the first day, the
# month it falls in (shared with the end of the range unless stated) and the year.
_DATE = re.compile(rf"(\d{{1,2}})(?:\s+({_MONTH}))?.*?({_MONTH})\s+(\d{{4}})$")


def _first_inspection_day(written: str) -> date:
    m = _DATE.match(written)
    if m is None:
        raise ValueError(f"inspection date not recognised: {written!r}")
    day, first_month, last_month, year = m.groups()
    return datetime.strptime(f"{day} {first_month or last_month} {year}", "%d %B %Y").date()


def parse_cover(text: str, kind: ReportKind) -> Cover:
    text = " ".join(text.split())  # collapse wrapped labels and values
    m = PATTERN.search(text)
    if m is None:
        raise ValueError("cover labels not found")
    name, provider, address, inspection_type, inspection_date, centre_id, fieldwork_id = (
        g.strip() for g in m.groups()
    )
    return Cover(
        centre_name=name,
        provider=provider,
        address=address,
        inspection_type=inspection_type,
        inspection_date=_first_inspection_day(inspection_date),
        centre_id=centre_id,
        fieldwork_id=fieldwork_id,
        service_type=ServiceType(kind.value),
    )
