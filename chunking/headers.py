from ingestion.models import CompliancePlanItem, Cover, ProviderResponse, RegulationFinding


def base_header(cover: Cover, county: str | None = None) -> str:
    """Fixed part of every chunk header: '<centre>, <county>, <date>.' (county omitted when unknown)."""
    d = cover.inspection_date
    parts = [cover.centre_name, county, f"{d.day} {d:%B %Y}"]
    return ", ".join(p for p in parts if p) + "."


def finding_header(cover: Cover, regulation_finding: RegulationFinding, county: str | None = None) -> str:
    judgment = regulation_finding.judgment.value.replace("_", " ").capitalize()
    return (
        f"{base_header(cover, county)} "
        f"Regulation {regulation_finding.regulation_number}: {regulation_finding.title}. {judgment}."
    )


def provider_response_header(cover: Cover, response: ProviderResponse, county: str | None = None) -> str:
    return (
        f"{base_header(cover, county)} "
        f"Provider's response to Regulation {response.regulation_number}: {response.title}."
    )


def compliance_item_header(cover: Cover, item: CompliancePlanItem, county: str | None = None) -> str:
    # regulation_ref already reads "Regulation 28(1)(b)" or "Registration Regulation 7(3)"
    parts = [f"Compliance plan, {item.regulation_ref}."]
    if item.risk_rating:
        parts.append(f"Risk rating: {item.risk_rating.value}.")
    if item.due_date:
        parts.append(f"Due {item.due_date.day} {item.due_date:%B %Y}.")
    return f"{base_header(cover, county)} " + " ".join(parts)


def summary_header(cover: Cover, county: str | None = None) -> str:
    return f"{base_header(cover, county)} Inspection summary."


def about_header(cover: Cover, county: str | None = None) -> str:
    return f"{base_header(cover, county)} About the centre."


# keyed by the Narrative field the text came from
NARRATIVE_LABELS = {
    "what_residents_told_us": "What residents told inspectors and what inspectors observed.",
    "capacity_intro": "Capacity and capability overview.",
    "quality_intro": "Quality and safety overview.",
}


def narrative_header(cover: Cover, field: str, county: str | None = None) -> str:
    return f"{base_header(cover, county)} {NARRATIVE_LABELS[field]}"
