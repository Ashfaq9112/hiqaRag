from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ServiceType(StrEnum):
    NURSING_HOME = "nursing_home"
    DISABILITY_ADULTS = "disability_adults"
    DISABILITY_CHILDREN = "disability_children"
    DISABILITY_MIXED = "disability_mixed"


class Judgment(StrEnum):
    COMPLIANT = "compliant"
    SUBSTANTIALLY_COMPLIANT = "substantially_compliant"
    NOT_COMPLIANT = "not_compliant"

    @classmethod
    def _missing_(cls, value: object) -> "Judgment | None":
        # "Not Compliant", "Substantially\nCompliant" -> "not_compliant", ...
        if isinstance(value, str):
            return cls._value2member_map_.get("_".join(value.lower().split()))
        return None


class Dimension(StrEnum):
    CAPACITY_AND_CAPABILITY = "capacity_and_capability"
    QUALITY_AND_SAFETY = "quality_and_safety"


class RegulationSeries(StrEnum):
    # "Regulation 5" (care) and "Registration Regulation 5" are different laws that reuse the same numbers
    CARE = "care"
    REGISTRATION = "registration"


class InspectionType(StrEnum):
    ANNOUNCED = "announced"
    UNANNOUNCED = "unannounced"
    SHORT_NOTICE_ANNOUNCED = "short_notice_announced"

    @classmethod
    def _missing_(cls, value: object) -> "InspectionType | None":
        if isinstance(value, str):
            return cls._value2member_map_.get("_".join(value.lower().split()))
        return None

class Cover(BaseModel):
    centre_name: str
    provider: str
    address: str
    inspection_type: InspectionType
    inspection_date: date
    centre_id: str
    fieldwork_id: str
    service_type: ServiceType


class RegulationFinding(BaseModel):
    series: RegulationSeries
    regulation_number: str
    title: str
    dimension: Dimension
    text: str
    judgment: Judgment


class RiskRating(StrEnum):
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"

    @classmethod
    def _missing_(cls, value: object) -> "RiskRating | None":
        # the PDF writes "Yellow"/"Orange"/"Red"
        if isinstance(value, str):
            return cls._value2member_map_.get(value.strip().lower())
        return None

class AppendixRow(BaseModel):
    series: RegulationSeries
    regulation_number: str
    title: str
    dimension: Dimension
    judgment : Judgment


class ProviderResponse(BaseModel):
    series: RegulationSeries
    regulation_number: str
    title : str
    judgment : Judgment
    response_text : str


class CompliancePlanItem(BaseModel):
    regulation_ref: str
    series: RegulationSeries
    regulation_number: str
    requirement: str
    judgment: Judgment
    risk_rating: RiskRating | None = None
    due_date: date | None = None


class CompliancePlan(BaseModel):
    responses: list[ProviderResponse]
    items: list[CompliancePlanItem]


class Narrative(BaseModel):
    how_we_inspect: str | None = None
    what_residents_told_us: str | None = None
    capacity_intro: str | None = None
    quality_intro: str | None = None


class ParsedReport(BaseModel):
    source_file: str
    cover: Cover
    about_centre: str
    residents_on_date: int | None = None
    narrative: Narrative
    findings: list[RegulationFinding]
    appendix: list[AppendixRow]
    compliance_plan: CompliancePlan | None = None
    parse_warnings: list[str] = Field(default_factory=list)