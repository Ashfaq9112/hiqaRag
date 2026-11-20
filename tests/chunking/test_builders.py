"""Tests for the provider_response, compliance_item and summary builders.

They use real parsed reports (read from data/parsed, skipped if missing), like the real-PDF ingestion tests:
  St Dominic's  has a compliance plan: 6 provider responses, 8 plan items, 12 appendix rows (6/2/4).
  Loughtown House has no compliance plan (every regulation compliant).
"""
from pathlib import Path

import pytest

from chunking.builders import build_compliance_item_chunks, build_provider_response_chunks, build_summary_chunk
from chunking.models import ChunkType
from ingestion.models import Dimension, Judgment, ParsedReport, RiskRating

PARSED = Path("data/parsed/reports_narr.jsonl")
ST_DOMINICS = "DIS_2023_1507-st-dominics-services-18-october-2023.pdf"
LOUGHTOWN = "DIS_2023_3363-loughtown-house-29-august-2023.pdf"  # no compliance plan


def load_report(source_file: str) -> ParsedReport:
    if not PARSED.exists():
        pytest.skip("parsed reports not on disk")
    with open(PARSED, encoding="utf-8") as f:
        for line in f:
            if source_file in line:
                return ParsedReport.model_validate_json(line)
    pytest.skip(f"{source_file} not in {PARSED}")


def make_base(report: ParsedReport) -> dict:
    cover = report.cover
    return {"centre_id": cover.centre_id, "centre_name": cover.centre_name, "inspection_date": cover.inspection_date,
            "service_type": cover.service_type, "provider": cover.provider, "county": "Galway"}


@pytest.fixture(scope="module")
def st_dominics() -> ParsedReport:
    return load_report(ST_DOMINICS)


@pytest.fixture(scope="module")
def no_plan() -> ParsedReport:
    report = load_report(LOUGHTOWN)
    assert report.compliance_plan is None  # the premise of the tests that use it
    return report


# ---- provider_response ----

def test_provider_responses_one_group_per_response(st_dominics):
    chunks = build_provider_response_chunks(st_dominics, make_base(st_dominics))
    keys = {c.chunk_id.rsplit(":", 1)[0] for c in chunks}  # chunk_id without the part number
    assert keys == {f"MON-0041321:provider_response:care-{n}" for n in ("15", "23", "26", "29", "5", "7")}
    assert {c.chunk_type for c in chunks} == {ChunkType.PROVIDER_RESPONSE}


def test_provider_response_metadata_and_header(st_dominics):
    chunks = build_provider_response_chunks(st_dominics, make_base(st_dominics))
    staffing = next(c for c in chunks if c.chunk_id == "MON-0041321:provider_response:care-15:0")
    assert staffing.regulation_title == "Staffing"
    assert staffing.judgment == Judgment.NOT_COMPLIANT
    assert staffing.dimension == Dimension.CAPACITY_AND_CAPABILITY  # borrowed from the finding
    assert staffing.risk_rating is None  # risk rating only exists on plan items
    assert staffing.embed_text.startswith(
        "St Dominic's Services, Galway, 18 October 2023. Provider's response to Regulation 15: Staffing.\n")
    assert staffing.display_text in staffing.embed_text
    assert "Provider's response" not in staffing.display_text  # the header is not shown to the user


def test_long_provider_response_is_split_into_numbered_parts(st_dominics):
    chunks = build_provider_response_chunks(st_dominics, make_base(st_dominics))
    governance = [c for c in chunks if ":care-23:" in c.chunk_id]  # a 5,000+ character response
    assert len(governance) > 1
    assert [c.part for c in governance] == list(range(len(governance)))
    assert len({c.embed_text.split("\n")[0] for c in governance}) == 1  # every part carries the same header


def test_no_compliance_plan_gives_no_provider_responses(no_plan):
    assert build_provider_response_chunks(no_plan, make_base(no_plan)) == []


# ---- compliance_item ----

def test_one_compliance_chunk_per_plan_item(st_dominics):
    chunks = build_compliance_item_chunks(st_dominics, make_base(st_dominics))
    assert len(chunks) == len(st_dominics.compliance_plan.items) == 8
    assert "MON-0041321:compliance_item:care-23(1)(a):0" in {c.chunk_id for c in chunks}


def test_compliance_item_metadata_and_header(st_dominics):
    chunks = build_compliance_item_chunks(st_dominics, make_base(st_dominics))
    item = next(c for c in chunks if c.chunk_id == "MON-0041321:compliance_item:care-23(1)(a):0")
    assert item.regulation_number == "23"  # the base number, so it links to the finding
    assert item.regulation_title == "Governance and management"  # looked up from the finding
    assert item.dimension == Dimension.CAPACITY_AND_CAPABILITY
    assert item.risk_rating == RiskRating.ORANGE
    assert item.embed_text.startswith(
        "St Dominic's Services, Galway, 18 October 2023. Compliance plan, Regulation 23(1)(a). "
        "Risk rating: orange. Due 1 December 2023.\n")
    assert item.display_text.startswith("The registered provider shall ensure")


def test_compliance_item_without_a_matching_finding_drops_all_three_regulation_fields(st_dominics):
    no_findings = st_dominics.model_copy(update={"findings": []})
    chunks = build_compliance_item_chunks(no_findings, make_base(no_findings))
    assert len(chunks) == 8  # still built, and Chunk's validator did not raise
    for c in chunks:
        assert (c.series, c.regulation_number, c.regulation_title, c.dimension) == (None, None, None, None)
        assert c.risk_rating is not None  # the rest of the metadata is kept


def test_no_compliance_plan_gives_no_compliance_items(no_plan):
    assert build_compliance_item_chunks(no_plan, make_base(no_plan)) == []


# ---- summary ----

def test_summary_is_one_chunk_with_the_right_counts(st_dominics):
    chunks = build_summary_chunk(st_dominics, make_base(st_dominics))
    assert len(chunks) == 1
    summary = chunks[0]
    assert summary.chunk_id == "MON-0041321:summary:0"
    assert summary.chunk_type == ChunkType.SUMMARY
    assert summary.embed_text.startswith("St Dominic's Services, Galway, 18 October 2023. Inspection summary.\n")
    text = summary.display_text
    assert "St Dominic's Services is run by Ability West." in text
    assert "This was an unannounced inspection on 18 October 2023." in text
    assert "6 residents lived there on the day." in text
    assert "Of 12 regulations considered, 6 were compliant, 2 substantially compliant and 4 not compliant." in text
    assert "Not compliant: Regulation 15: Staffing;" in text
    assert "Substantially compliant: Regulation 29: Medicines and pharmaceutical services;" in text


def test_summary_without_resident_count_leaves_that_sentence_out(st_dominics):
    report = st_dominics.model_copy(update={"residents_on_date": None})
    text = build_summary_chunk(report, make_base(report))[0].display_text
    assert "residents lived there" not in text
    assert "None" not in text


def test_summary_with_no_problems_has_no_not_compliant_list(no_plan):
    text = build_summary_chunk(no_plan, make_base(no_plan))[0].display_text
    assert "0 not compliant" in text
    assert "Not compliant:" not in text
