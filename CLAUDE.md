# How to Act and Instructions

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

# HIQA RAG — Project Context

## What This Is

A production-level RAG + Agentic system built on HIQA (Health Information and Quality Authority) inspection reports — Ireland's independent healthcare regulator. The system lets users ask natural-language questions about nursing home and disability service inspections and get grounded, cited answers.

This is a portfolio/CV project demonstrating a full production RAG stack. The developer is based in Cork, Ireland.

## Who Benefits

- Families choosing nursing homes or disability services for relatives
- Journalists investigating care quality patterns
- Compliance officers tracking regulatory trends
- Advocacy groups monitoring standards across regions

## Data Source

**HIQA Inspection Reports** — publicly available PDFs from https://www.hiqa.ie/reports-and-publications/inspection-reports

### Phase 1 scope (current): Two service types with identical report templates
- **Designated Centres for Older People** (nursing homes) — S.I. No. 415 of 2013
- **Designated Centres for People with Disabilities** — S.I. No. 367 of 2013

### Phase 2 scope (future): Additional service types with different templates
- Healthcare (hospital inspections) — National Standards for Safer Better Healthcare
- Children's Services — National Standards for Children's Residential Centres
- Ionising Radiation (MEIR) — Medical Exposure Ionising Radiation Regulations

### Report Structure (Nursing Homes + Disability — same template)
Verified by hand on 24 sample reports (2023–2026) plus a scripted check of the text layer. Text is selectable in every sample (no OCR needed); reports run 12–30 pages.
1. **Cover page** — title line, then labelled fields: centre name, provider, address (free text, county not a separate field), type of inspection (announced/unannounced), date of inspection, Centre ID (OSV-…), Fieldwork ID (MON-…). Labels and values wrap across lines. **No inspector names on the cover.** The cover title is the reliable service-type signal: "Designated Centre for Older People" or "Designated Centre for Disabilities (Adults|Children)".
2. **About the designated centre** — provider-submitted paragraph, then "Number of residents on the date of inspection".
3. **How we inspect** — paragraphs and bullets, then the **inspection times table** (date, times, inspector, role Lead/Support). This is where inspector names live. **Decision: not extracted** (no inspector data in the model); the narrative text is kept, the table is skipped.
4. **What residents told us and what inspectors observed** — narrative paragraphs, no regulation or judgment.
5. **Capacity and capability** and 6. **Quality and safety** — each opens with narrative paragraphs, then regulation blocks: "Regulation N: Title", prose, "Judgment: Compliant|Substantially compliant|Not compliant". Some sections are narrative only (no regulation heading or judgment).
7. **Appendix 1 — Full list of regulations considered under each dimension** — table of Regulation Title + Judgment only. **No risk rating here.**
8. **Compliance Plan for <centre>** — **only present if at least one regulation is not fully compliant.** Section 1: provider's response, one block per non-compliant regulation with three parts: regulation heading, judgment, and a long response text (begins after the line `Outline how you are going to come into compliance with Regulation N: <title>:`). Section 2: regulations to be complied with (Regulation, requirement, Judgment, **Risk rating**, date to be complied with). Risk rating exists only here.

Parsing traps found in the samples:
- Absence of a compliance plan is valid data (all compliant), not an error.
- Do not detect non-compliance by searching the whole text: prose mentions earlier inspections ("found this service not compliant"). Use `Judgment:` lines and the Appendix table.
- Judgment casing varies ("Not compliant" in body, "Not Compliant" in tables); normalise.
- Regulation numbers differ in meaning between service types (Reg 5: "...care plan" vs "...personal plan"; Reg 7: "Managing behaviour that is challenging" vs "Positive behavioural support"). Always store `service_type` with the regulation number.
- Disability has two sub-types (Adults, Children).
- Folder names are not a reliable service-type label; use the cover title.
- **Thematic inspections exist** (e.g. "Report of a Restrictive Practice Thematic Inspection of a Designated Centre for Older People") with a different template: starts with "What is a thematic inspection?", no regulation blocks, no judgments, no compliance plan. **Decision: exclude them in Phase 1** (detect via cover title) and log how many are skipped during download.

PDF layout facts (verified on 24 samples, 2023–2026, both service types; template unchanged across years):
- Style roles (Tahoma): section heading = bold + white + ~14pt on a blue box; subheading = bold black 12pt; body = 12pt; `Judgment:` lines = 11pt; footer = 9pt. Sizes drift by ~0.1 (14.0 vs 13.9), so match with a tolerance, never `==`.
- Bullets are glyph fonts (SymbolMT, Wingdings, CourierNew; chars like ``); normalise.
- Tables exist only for: inspector times (ignored), Appendix 1, compliance plan Section 1 header and Section 2. Regulation findings are plain text.
- `find_tables()` output is messy: split headers, `None` cells, line breaks inside cells, and **column positions shift between files** (read non-empty cells in order, never by index). Section 2 rows continue across page breaks.
- Risk rating is text (`Yellow`/`Orange`/`Red`) in Section 2; no colour detection needed. Section 1 provider actions are plain text, not a table.
- Section 1 parsing (verified on nursing + disability 2024-2): `find_tables()` catches the heading/judgment (and sometimes the "Outline how…" row) only for the first block; later blocks are plain text. The response text is never in a table and often runs across page breaks (bullets as `•`/`�` glyphs). Split blocks on the `Regulation N:` heading, anchored by the "Outline how you are going to come into compliance with…" line, ending at `Section 2`. Skip the identical "Section 1" intro boilerplate (SMART explanation). Judgment casing here is "Substantially Compliant" (normalise).
- Section 1 has one response per regulation (`Regulation 17`); Section 2 can have several rows for it (`17(1)`, `17(2)`). Link on the base number.
- The cover is a table in some files (garbled spacing: `N ame of d esi gnated`) and not in others; read it from plain text, not `find_tables()`.
- Findings use `Regulation 28: Fire precautions`; the compliance plan uses `Regulation 28(1)(b)`; link them on the base number.
- Thematic inspections use a different style set (headings bold 14 in dark blue `#000099`, no size-11 Judgment lines).
- Not yet verified: pre-2023 reports.

### Corpus size
- ~7,000+ reports on hiqa.ie (search index goes to 735+ pages)
- ~2,000 new inspections per year (2,116 in 2025)
- ~580+ nursing home centres, ~1,400+ disability centres

## Tech Stack Decisions

These choices were made deliberately — be ready to explain the reasoning in interviews.

### PDF Parsing


### Chunking Strategy (**Still Need to test and confrm**)
- **Structure-aware chunking** — HIQA's consistent template allows deterministic section-based splitting. The parser's own units (`RegulationFinding`, `ProviderResponse`, `CompliancePlanItem`, `AppendixRow`, narrative fields) are the chunk boundaries; no heuristics needed.
- **Chunk types:** `finding` (one per regulation per report), `provider_response`, `compliance_item`, `summary` (cover + appendix as sentence-style text, not a flattened table), `about`, `narrative` (what residents told us, capacity/quality intros).
- **Skip "How we inspect"**: identical 470-token boilerplate in every report; embedding it would fill the index with near-duplicates.
- Target: ~400 tokens per chunk (leaves room for the header under bge-large's 512-token limit), counted with the embedding model's own tokenizer. Split only what exceeds the budget, at sentence boundaries, ~50-token overlap, never across two regulations; every part keeps the same metadata and header. Use LangChain's `RecursiveCharacterTextSplitter` (`langchain-text-splitters` only) for this oversized-chunk split and nothing else.
- Measured on 378 reports (rough tokens): finding median 104 / p99 746; provider response median 134 / p99 1,080; "what residents told us" median 1,184 (must be split).
- **Context header (contextual retrieval, deterministic):** every chunk gets a short header built from parsed fields by a per-chunk-type template, no LLM. `embed_text = header + "\n" + display_text`. The LLM and the user only see `display_text`. Fixed part: `<centre>, <county>, <date>.` Variable part by type, omitting anything that doesn't apply (never "None"):
  - finding: `Regulation 14: Persons in charge. Not compliant.`
  - provider_response: `Provider's response to Regulation 14: Persons in charge.`
  - compliance_item: `Compliance plan, Regulation 14(1)(a). Risk rating: orange. Due 1 May 2025.`
  - summary / about / narrative: `Inspection summary.` / `About the centre.` / `What residents told inspectors and what inspectors observed.`
- **Contextual BM25:** the same `embed_text` (header included) feeds both the embedding and the Postgres `tsvector`, so exact centre/regulation words are keyword-searchable. Basis: Anthropic's Contextual Retrieval (vendor-reported: top-20 failures -35% embeddings only, -49% with contextual BM25, -67% with reranking).
- **Metadata per chunk (real, indexed columns used for filtering; NULL where not applicable):** chunk_id (readable deterministic key: `fieldwork_id:chunk_type:regulation key:part`, e.g. `MON-0012345:finding:care-14:0`), report_id (= `fieldwork_id`), chunk_type, part, centre_id, centre_name, county (extract from address free text), service_type (nursing_home/disability_adults/disability_children/disability_mixed), provider, inspection_date, series + regulation_number + regulation_title (always together), dimension, judgment, risk_rating, chunker_version, content_hash.
- Validate after chunking: report chunks over the token budget (silent truncation is a classic bug), empty/tiny chunks (<20 tokens), required metadata present.

**The Below stack are not yet confirmed**

### Embedding
- **`BAAI/bge-large-en-v1.5`** or **`voyage-3`** — strong on regulatory/domain text
- Index type: HNSW

### Vector Database
- **pgvector on PostgreSQL** — chosen over Pinecone/Weaviate because:
  - Interviewers respect "real infrastructure"
  - Native full-text search (tsvector) for BM25-style sparse retrieval in the same DB
  - Single data store for vectors + metadata + structured queries
  - Production-grade, battle-tested

### Retrieval
- **Hybrid: dense (pgvector) + sparse (PostgreSQL FTS/BM25)**
- Fusion: Reciprocal Rank Fusion (RRF, k=60)
- Retrieve ~50 candidates before reranking
- Metadata filters applied before search (county, date range, service type, compliance rating)
- **Query parsing (self-query):** an LLM turns the natural-language question into a Pydantic `QueryFilters` (service_type, county, centre, year range, judgment, regulation_number, `search_text`) via structured output; `None` for anything the question doesn't state. Validate against known values, resolve centre names to `centre_id` with fuzzy matching (`pg_trgm`) over a centres table, pass today's date for relative dates, fall back (drop the weakest filter, then no filters) on empty results, and show the user which filters were applied. UI dropdown filters, when present, override or merge with the extracted ones.

### Reranking
- **`BAAI/bge-reranker-v2-m3`** via sentence-transformers CrossEncoder
- 50 candidates -> reranker -> top 5 to LLM
- "Cheapest big quality win" — but cannot compensate for bad chunking



### Agentic Layer
- Plain tool-use function calling (or LangGraph for CV value)
- Tools: Needed to be decided; likely `search_findings`, `compare_centres`, `trend` (a centre's judgment on a regulation across years)
- **No GraphRAG / graph database.** The relationships (centre -> report -> regulation -> finding -> provider response -> compliance item, and centre across years) are known from the template, so they are modelled relationally in Postgres (`centre_id`, `regulation_number`, `inspection_date`) and exposed as agent tools. Interview answer: considered GraphRAG, chose relational joins because the entities are known, not discovered.
  

### Evaluation
- **Golden test set:** 50-100 manually curated question/answer pairs from real reports
- **Retrieval metrics:** Recall@5 (target >= 0.85), MRR, nDCG@5
- **Generation metrics (RAGAS):** faithfulness, answer_relevancy, context_precision
- Run in CI on every corpus change
- **Ablations (later, if time permits):** dense only vs + header vs + contextual BM25 (RRF) vs + reranker; header vs LLM-generated context for narrative chunks; late chunking; agentic vs single-shot hybrid on multi-step questions (compare/trend). Report Recall@5 and MRR for each.


## Build Order

1. **Ingestion & Parsing** — PDF to structured chunks with metadata
2. **Chunking** — structure-aware, section-based splitting
3. **Embedding & Indexing** — pgvector + PostgreSQL FTS setup
4. **Hybrid Retrieval** — dense + sparse with RRF fusion
5. **Reranking** — cross-encoder on candidate set
6. **Generation** — grounded answers with citations
7. **Agentic Layer** — multi-tool reasoning (compare, trend, filter)
8. **Evaluation** — RAGAS metrics, golden test set
9. **Observability & Deployment** — logging, caching, API, frontend

## Code Style

- Python 3.11+
- Type hints everywhere
- Pydantic models for data structures
- async where it makes sense (FastAPI endpoints, batch embedding)
- Clean separation: ingestion / chunking / retrieval / generation / agents as separate modules
- Tests in a top-level `tests/` folder that mirrors the modules (`tests/ingestion/`, ...)
- Environment variables for API keys and config (never hardcoded)
- Use `uv` or `poetry` for dependency management

## Key Principles

- **Every architectural choice must be explainable in an interview.** No black boxes.
- **Retrieval quality > generation quality.** "Retrieval is the culprit ~73% of the time when RAG fails."
- **Chunking is where quality is won or lost.** Get this right before optimizing downstream.
- **Evaluate everything with numbers.** No "it seems to work" — measure Recall@5, faithfulness, precision.
- **Ground every answer in source data.** Citations are not optional.
- **Build incrementally.** Ship a working baseline, then add hybrid retrieval, then reranking, measuring lift at each stage.



# Session Log (Google Drive)

At the end of every session, create a NEW Google Doc in the Drive folder `claude memories/hiqa rag` (folder id `13GtsxgW6rW_HnPIX5yW4peu1HbKPmTPZ`) titled `Session log YYYY-MM-DD`, with what we did and what we learnt (short, with numbers). The Drive connector can create files but cannot edit a doc's contents, so never try to append to an existing one. `HIQA RAG - project timeline and learnings` (id `1VroSFA8qbZ4paQHSa2zA97yP-uXz8G07Hv5RTrqj8gQ`) is the baseline up to 2026-11-17. A scheduled Claude reads this folder to remind the user to post on LinkedIn, so keep entries factual and free of personal details. When the user mentions a LinkedIn post, record it in a new file `Posting history YYYY-MM-DD` in the same folder.
