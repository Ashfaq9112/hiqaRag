from datetime import date

from chunking.headers import (
    about_header,
    base_header,
    compliance_item_header,
    finding_header,
    narrative_header,
    provider_response_header,
    summary_header,
)
from ingestion.models import (
    CompliancePlanItem,
    Cover,
    Dimension,
    InspectionType,
    Judgment,
    ProviderResponse,
    RegulationFinding,
    RegulationSeries,
    RiskRating,
    ServiceType,
)


def make_cover() -> Cover:
    return Cover(
        centre_name="Ave Maria Nursing Home",
        provider="Ave Maria Ltd",
        address="Cork",
        inspection_type=InspectionType.UNANNOUNCED,
        inspection_date=date(2025, 3, 2),
        centre_id="OSV-0000001",
        fieldwork_id="MON-0000001",
        service_type=ServiceType.NURSING_HOME,
    )


def test_base_header_with_county() -> None:
    assert base_header(make_cover(), "Cork") == "Ave Maria Nursing Home, Cork, 2 March 2025."


def test_base_header_without_county() -> None:
    assert base_header(make_cover()) == "Ave Maria Nursing Home, 2 March 2025."


def test_finding_header() -> None:
    finding = RegulationFinding(
        series=RegulationSeries.CARE,
        regulation_number="14",
        title="Persons in charge",
        dimension=Dimension.CAPACITY_AND_CAPABILITY,
        text="...",
        judgment=Judgment.NOT_COMPLIANT,
    )
    assert finding_header(make_cover(), finding, "Cork") == (
        "Ave Maria Nursing Home, Cork, 2 March 2025. Regulation 14: Persons in charge. Not compliant."
    )


BASE = "Ave Maria Nursing Home, Cork, 2 March 2025."


def test_provider_response_header() -> None:
    response = ProviderResponse(
        series=RegulationSeries.CARE,
        regulation_number="14",
        title="Persons in charge",
        judgment=Judgment.NOT_COMPLIANT,
        response_text="...",
    )
    assert provider_response_header(make_cover(), response, "Cork") == (
        f"{BASE} Provider's response to Regulation 14: Persons in charge."
    )


def test_compliance_item_header() -> None:
    item = CompliancePlanItem(
        regulation_ref="Regulation 14(1)(a)",
        series=RegulationSeries.CARE,
        regulation_number="14",
        requirement="...",
        judgment=Judgment.NOT_COMPLIANT,
        risk_rating=RiskRating.ORANGE,
        due_date=date(2025, 5, 1),
    )
    assert compliance_item_header(make_cover(), item, "Cork") == (
        f"{BASE} Compliance plan, Regulation 14(1)(a). Risk rating: orange. Due 1 May 2025."
    )


def test_summary_about_narrative_headers() -> None:
    cover = make_cover()
    assert summary_header(cover, "Cork") == f"{BASE} Inspection summary."
    assert about_header(cover, "Cork") == f"{BASE} About the centre."
    assert narrative_header(cover, "what_residents_told_us", "Cork") == (
        f"{BASE} What residents told inspectors and what inspectors observed."
    )
