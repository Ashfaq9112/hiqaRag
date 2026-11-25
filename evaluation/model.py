from pydantic import BaseModel, Field
from chunking.models import ChunkType, ServiceType, Judgment

class Unit(BaseModel):
    base_key: str            # "MON-0012345:finding:care-28"
    text: str                # part 0 + part 1 joined
    header: str              # the context header (centre, county, date, regulation, judgment, risk rating...)
    token_count: int         # sum over the parts
    chunk_type: ChunkType
    centre_id: str
    centre_name: str
    county: str | None
    year: int
    service_type: ServiceType
    judgment: Judgment | None
    regulation_key: str      # "care-28", or "" for summary
    regulation_title: str | None

class Job(BaseModel):
    unit_key : str
    persona : str
    style : str
    intent : str             # key into INTENTS[chunk_type]: what the question asks about


QUOTAS: dict[ChunkType, int] = {
    ChunkType.FINDING: 45,
    ChunkType.PROVIDER_RESPONSE: 25,
    ChunkType.COMPLIANCE_ITEM: 25,
    ChunkType.SUMMARY: 20,
    ChunkType.NARRATIVE: 20,
    ChunkType.ABOUT: 15,
}

PERSONAS_BY_TYPE: dict[ChunkType, list[str]] = {
    ChunkType.FINDING: ["family member", "journalist", "compliance officer", "advocacy worker"],
    ChunkType.PROVIDER_RESPONSE: ["journalist", "compliance officer", "advocacy worker"],
    ChunkType.COMPLIANCE_ITEM: ["compliance officer", "journalist"],
    ChunkType.SUMMARY: ["family member", "advocacy worker", "journalist"],
    ChunkType.NARRATIVE: ["family member", "journalist"],
    ChunkType.ABOUT: ["family member"],
}

STYLES: list[str] = ["paraphrase", "keyword"]   # wording only, never changes what is asked

# What the question asks about. name -> instruction sent to the LLM.
INTENTS: dict[ChunkType, dict[str, str]] = {
    ChunkType.FINDING: {
        "judgment": "Ask whether the centre was compliant, substantially compliant or not compliant on this regulation. The judgment is in the first line of the passage.",
        "shortcoming": "Ask what specific problem, or what specific good practice, the inspectors found.",
        "how_it_works": "Ask how the centre handles this area day to day, or what the inspectors checked.",
    },
    ChunkType.PROVIDER_RESPONSE: {
        "actions": "Ask what actions the provider said it would take.",
        "dates": "Ask by when the provider said something would happen. Use a date or time frame stated in the passage.",
        "specific_step": "Pick one specific step (for example hiring, training, repairs, a review) and ask whether the provider committed to it.",
    },
    ChunkType.COMPLIANCE_ITEM: {
        "risk_rating": "Ask what risk rating the inspectors gave. The rating is in the first line of the passage.",
        "due_date": "Ask by when the centre had to comply. The due date is in the first line of the passage.",
        "requirement": "Ask what the provider must ensure under this regulation.",
    },
    ChunkType.SUMMARY: {
        "counts": "Ask how many regulations were compliant, substantially compliant or not compliant.",
        "which_failed": "Ask which regulations the centre was not compliant (or substantially compliant) with.",
        "inspection_facts": "Ask how many residents lived there on the day, or whether the inspection was announced.",
    },
    ChunkType.ABOUT: {
        "capacity": "Ask how many residents the centre can support, or how many beds it has.",
        "facilities": "Ask what the centre offers or looks like: respite, rooms, garden, transport.",
        "staffing": "Ask who supports the residents, or who the centre is for.",
    },
    ChunkType.NARRATIVE: {
        "event_or_decision": "Pick one concrete event, decision or action described in the passage and ask about it.",
        "observation_or_concern": "Pick one concern, observation or comment from residents or inspectors and ask about it.",
    },
}


class LlmOutput(BaseModel):
    eval_ques: str = Field(description="The question, worded the way the persona would ask it")
    evidence_quote: str = Field(description="The exact sentence(s) copied word for word from the passage that answer the question")
    