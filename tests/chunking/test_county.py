import json
from pathlib import Path

import pytest

from chunking.country_extracter import extract_county

PARSED = Path("data/parsed/reports_narr.jsonl")


@pytest.mark.parametrize("address, expected", [
    ("Mountain Road, Tubbercurry, Sligo", "Sligo"),  # the normal shape: county is the last piece
    ("Cork", "Cork"),  # address is just the county
    ("Dublin 13", "Dublin"),  # postal district
    ("Dublin 6w", "Dublin"),  # district with a letter
    ("Co. Dublin", "Dublin"),  # "Co." prefix
    ("Kellystown Road, Rathfarnham, Dublin 16", "Dublin"),
    ("Dublin Road, Thurles, Tipperary", "Tipperary"),  # street named after another county
    ("49 Meath Road, Bray, Wicklow", "Wicklow"),
    ("Old Dublin Road, Carlow, Carlow", "Carlow"),
    ("SLIGO", "Sligo"),  # returns the canonical spelling, not the text as written
])
def test_extract_county(address, expected):
    assert extract_county(address) == expected


def test_no_county_returns_none():
    assert extract_county("12 High Street, Springfield") is None


def test_county_name_inside_a_longer_word_does_not_match():
    assert extract_county("Corkagh Park, Clondalkin") is None  # "cork" is inside "corkagh" but is not that word


@pytest.mark.skipif(not PARSED.exists(), reason="parsed reports not on disk")
def test_every_real_address_gets_a_county():
    with open(PARSED, encoding="utf-8") as f:
        missing = [a for a in (json.loads(line)["cover"]["address"] for line in f) if extract_county(a) is None]
    assert missing == []
