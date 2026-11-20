from collections import Counter
from chunking.country_extracter import extract_county
from chunking.models import Chunk, ChunkType
from chunking.tokens import count_tokens
from chunking.splitter import split_text
from chunking.ids import chunk_id, content_hash
from chunking.headers import finding_header, about_header, narrative_header,provider_response_header,compliance_item_header,summary_header
from ingestion.models import Dimension, Judgment, ParsedReport

def make_chunks(report_id, chunk_type, key, header, text, metadata) -> list[Chunk]:
    chunks = []
    for part, piece in enumerate(split_text(text)):
        embed_text = header + "\n" + piece 
        chunks.append(Chunk(
            chunk_id=chunk_id(report_id, chunk_type,key, part), report_id=report_id, chunk_type=chunk_type, part=part,
            display_text=piece, embed_text=embed_text, token_count=count_tokens(embed_text),
            content_hash=content_hash(embed_text), chunker_version="1", **metadata,
        ))
    return chunks





def build_finding_chunks(report, base):
    findings = report.findings
    chunks = []
    for finding in findings:
        metadata = {"series":finding.series,"regulation_number":finding.regulation_number,"regulation_title":finding.title,"dimension":finding.dimension,
                    "judgment":finding.judgment}
        header = finding_header(report.cover, regulation_finding=finding,county=base["county"])
        chunks.extend(make_chunks(report.cover.fieldwork_id,chunk_type=ChunkType.FINDING,key=f"{finding.series.value}-{finding.regulation_number}",header=header,text=finding.text,metadata={**base,**metadata}))


    return chunks


def build_about_chunks(report: ParsedReport, base: dict) -> list[Chunk]:
    if not report.about_centre:
        return []
    header = about_header(report.cover, county=base["county"])
    return make_chunks(report.cover.fieldwork_id, ChunkType.ABOUT, key="", header=header,
                       text=report.about_centre, metadata=base)


# Narrative field -> dimension it belongs to (None when it covers the whole report)
NARRATIVE_DIMENSIONS = {
    "what_residents_told_us": None,
    "capacity_intro": Dimension.CAPACITY_AND_CAPABILITY,
    "quality_intro": Dimension.QUALITY_AND_SAFETY,
}


def build_narrative_chunks(report: ParsedReport, base: dict) -> list[Chunk]:
    chunks = []
    for field, dimension in NARRATIVE_DIMENSIONS.items():
        text = getattr(report.narrative, field)
        if not text:
            continue
        header = narrative_header(report.cover, field, county=base["county"])
        chunks.extend(make_chunks(report.cover.fieldwork_id, ChunkType.NARRATIVE, key=field, header=header,
                                  text=text, metadata={**base, "dimension": dimension}))
    return chunks

def build_provider_response_chunks(report: ParsedReport, base: dict) -> list[Chunk]:
    if report.compliance_plan is None:  # all compliant: valid data, nothing to chunk
        return []
    # dimension is not on ProviderResponse, so borrow it from the finding with the same (series, number)
    dimensions = {(f.series, f.regulation_number): f.dimension for f in report.findings}
    chunks = []
    for response in report.compliance_plan.responses:
        metadata = {"series": response.series, "regulation_number": response.regulation_number,
                    "regulation_title": response.title, "judgment": response.judgment,
                    "dimension": dimensions.get((response.series, response.regulation_number))}
        header = provider_response_header(cover=report.cover, response=response, county=base["county"])
        chunks.extend(make_chunks(report.cover.fieldwork_id, ChunkType.PROVIDER_RESPONSE,
                                  key=f"{response.series.value}-{response.regulation_number}", header=header,
                                  text=response.response_text, metadata={**base, **metadata}))
    return chunks


def build_compliance_item_chunks(report: ParsedReport, base: dict) -> list[Chunk]:
    if report.compliance_plan is None:
        return []
    # CompliancePlanItem has no title or dimension: look both up from the finding on the base number
    findings = {(f.series, f.regulation_number): f for f in report.findings}
    chunks = []
    for item in report.compliance_plan.items:
        finding = findings.get((item.series, item.regulation_number))
        metadata = {"series": item.series, "regulation_number": item.regulation_number,
                    "regulation_title": finding.title if finding else None,
                    "dimension": finding.dimension if finding else None,
                    "judgment": item.judgment, "risk_rating": item.risk_rating}
        if finding is None:  # the series/number/title validator needs all three or none
            metadata.update(series=None, regulation_number=None)
        header = compliance_item_header(cover=report.cover, item=item, county=base["county"])
        # "Regulation 05(1)(b)" -> "5(1)(b)": drop the prefix and leading zeros so the key is stable
        ref = item.regulation_ref.rsplit("Regulation ", 1)[-1].lstrip("0")
        chunks.extend(make_chunks(report.cover.fieldwork_id, ChunkType.COMPLIANCE_ITEM,
                                  key=f"{item.series.value}-{ref}", header=header,
                                  text=item.requirement, metadata={**base, **metadata}))
    return chunks


def build_summary_chunk(report: ParsedReport, base: dict) -> list[Chunk]:
    cover = report.cover
    counts = Counter(row.judgment for row in report.appendix)
    sentences = [
        f"{cover.centre_name} is run by {cover.provider}.",
        f"This was an {cover.inspection_type.value.replace('_', ' ')} inspection on "
        f"{cover.inspection_date.day} {cover.inspection_date:%B %Y}.",
    ]
    if report.residents_on_date is not None:
        sentences.append(f"{report.residents_on_date} residents lived there on the day.")
    sentences.append(
        f"Of {len(report.appendix)} regulations considered, {counts[Judgment.COMPLIANT]} were compliant, "
        f"{counts[Judgment.SUBSTANTIALLY_COMPLIANT]} substantially compliant and "
        f"{counts[Judgment.NOT_COMPLIANT]} not compliant.")
    for judgment, label in ((Judgment.NOT_COMPLIANT, "Not compliant"),
                            (Judgment.SUBSTANTIALLY_COMPLIANT, "Substantially compliant")):
        rows = [f"Regulation {r.regulation_number}: {r.title}" for r in report.appendix if r.judgment == judgment]
        if rows:
            sentences.append(f"{label}: {'; '.join(rows)}.")
    return make_chunks(cover.fieldwork_id, ChunkType.SUMMARY, key="", header=summary_header(cover, county=base["county"]),
                       text=" ".join(sentences), metadata=base)




def build_chunks(parsed_report : ParsedReport):
    chunks = []
    cover = parsed_report.cover
    county  = extract_county(cover.address) # we need to decide here
    base = {
    "centre_id": cover.centre_id,
    "centre_name": cover.centre_name,
    "inspection_date": cover.inspection_date,
    "service_type": cover.service_type,
    "provider": cover.provider,
    "county": county}
    finding_chunks = build_finding_chunks(parsed_report,base)

    chunks.extend(finding_chunks)
    chunks.extend(build_about_chunks(parsed_report, base))
    chunks.extend(build_narrative_chunks(parsed_report, base))
    chunks.extend(build_provider_response_chunks(parsed_report, base))
    chunks.extend(build_compliance_item_chunks(parsed_report, base))
    chunks.extend(build_summary_chunk(parsed_report, base))

    return chunks

