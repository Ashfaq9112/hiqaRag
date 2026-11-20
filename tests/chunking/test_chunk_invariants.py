from datetime import date

import pytest

from chunking.models import Chunk, ChunkType
from ingestion.models import Dimension, Judgment, RegulationSeries, ServiceType
from tests.chunking.chunk_invariants import (
    DEFAULT_CHUNKS,
    KNOWN_EXCEPTIONS,
    all_violations,
    check_chunk,
    check_groups,
    load_chunks,
)

if not DEFAULT_CHUNKS.exists():
    pytest.skip("run `uv run python -m chunking.run_chunking` first", allow_module_level=True)

CHUNKS = load_chunks()


# ---- the real corpus ----

def test_corpus_has_no_new_violations():
    new = [v for v in all_violations(CHUNKS) if v not in KNOWN_EXCEPTIONS]
    assert new == []


def test_known_exceptions_are_still_real():
    assert KNOWN_EXCEPTIONS <= set(all_violations(CHUNKS))


def test_county_is_filled_in():
    assert all(c.county for c in CHUNKS)


# ---- the validator itself: feed it broken chunks and check it notices ----

HEADER = "Test Centre, 5 March 2025. Regulation 14: Persons in charge. Not compliant."
TEXT = "The person in charge did not have the required qualifications. " * 3


def good_finding() -> Chunk:
    return Chunk(
        chunk_id="MON-0000001:finding:care-14:0", report_id="MON-0000001", chunk_type=ChunkType.FINDING, part=0,
        display_text=TEXT, embed_text=HEADER + "\n" + TEXT, token_count=60,
        centre_id="OSV-0000001", centre_name="Test Centre", inspection_date=date(2025, 3, 5),
        service_type=ServiceType.NURSING_HOME, dimension=Dimension.CAPACITY_AND_CAPABILITY,
        judgment=Judgment.NOT_COMPLIANT, series=RegulationSeries.CARE, regulation_number="14",
        regulation_title="Persons in charge", chunker_version="1", content_hash="x",
    )


def test_good_chunk_passes():
    assert check_chunk(good_finding()) == []


@pytest.mark.parametrize("change, expected_check", [
    ({"token_count": 600}, "too_long"),
    ({"token_count": 10}, "too_short"),
    ({"display_text": "  "}, "empty_display_text"),
    ({"embed_text": "Test Centre, 5 March 2025.\n" + TEXT}, "header_missing:Regulation 14: Persons in charge. Not compliant."),
    ({"embed_text": HEADER.replace("5 March", "6 March") + "\n" + TEXT}, "header_missing_date"),
    ({"embed_text": HEADER.replace("Not compliant.", "None.") + "\n" + TEXT}, "header_contains_None"),
    ({"embed_text": "Other Place, 5 March 2025. Regulation 14: Persons in charge. Not compliant.\n" + TEXT},
     "header_does_not_start_with_centre_name"),
    ({"embed_text": HEADER}, "embed_text_is_not_header_plus_display_text"),
    ({"chunk_id": "MON-9999999:finding:care-14:0"}, "chunk_id_malformed"),
    ({"chunk_id": "MON-0000001:finding:care-15:0"}, "chunk_id_key_wrong_for_type"),
    ({"dimension": None}, "missing_dimension"),
    ({"risk_rating": "red"}, "unexpected_risk_rating"),
])
def test_validator_catches_broken_chunk(change, expected_check):
    broken = good_finding().model_copy(update=change)  # model_copy skips validation, so broken values get through
    assert (broken.chunk_id, expected_check) in check_chunk(broken)


def test_validator_catches_duplicate_ids():
    assert ("MON-0000001:finding:care-14:0", "duplicate_chunk_id") in check_groups([good_finding(), good_finding()])


def test_validator_catches_gap_in_parts():
    part_2 = good_finding().model_copy(update={"part": 2, "chunk_id": "MON-0000001:finding:care-14:2"})
    found = check_groups([good_finding(), part_2])
    assert ("MON-0000001:finding:care-14", "parts_not_0_to_n_minus_1") in found


def test_validator_catches_parts_that_disagree():
    part_1 = good_finding().model_copy(
        update={"part": 1, "chunk_id": "MON-0000001:finding:care-14:1", "judgment": Judgment.COMPLIANT})
    found = check_groups([good_finding(), part_1])
    assert ("MON-0000001:finding:care-14", "parts_disagree_on_judgment") in found
