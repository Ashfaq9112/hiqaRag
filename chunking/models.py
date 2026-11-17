from datetime import date
from enum import StrEnum

from pydantic import BaseModel, model_validator

from ingestion.models import Dimension, Judgment, RegulationSeries, RiskRating, ServiceType


class ChunkType(StrEnum):
    FINDING = "finding"
    PROVIDER_RESPONSE = "provider_response"
    COMPLIANCE_ITEM = "compliance_item"
    SUMMARY = "summary"
    ABOUT = "about"
    NARRATIVE = "narrative"


class Chunk(BaseModel):
    # identity
    chunk_id: str
    report_id: str
    chunk_type: ChunkType
    part: int = 0

    # text
    display_text: str
    embed_text: str
    token_count: int

    # always present
    centre_id: str
    centre_name: str
    inspection_date: date
    service_type: ServiceType

    # present when the source has it
    county: str | None = None
    provider: str | None = None
    dimension: Dimension | None = None
    judgment: Judgment | None = None
    risk_rating: RiskRating | None = None

    # regulation: all three set, or none
    series: RegulationSeries | None = None
    regulation_number: str | None = None
    regulation_title: str | None = None

    # versioning
    chunker_version: str
    content_hash: str

    @model_validator(mode="after")
    def regulation_fields_together(self) -> "Chunk":
        # the same number means different things per series/service type, so never store one alone
        set_count = sum(v is not None for v in (self.series, self.regulation_number, self.regulation_title))
        if set_count not in (0, 3):
            raise ValueError("series, regulation_number and regulation_title must be set together")
        return self
