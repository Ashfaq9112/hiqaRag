"""Quick look at what Gemini writes for a few jobs. Prints a short summary and writes one JSON line per job to a log.

Run:  uv run python -m evaluation.silver_try
Needs: uv add google-genai python-dotenv, and GEMINI_API_KEY in the .env file at the project root.
Log:   evaluation/out/silver_try_log.jsonl (appended; every row has a run_id)
"""
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from chunking.models import ChunkType
from evaluation.model import INTENTS, Job, LlmOutput, Unit
from evaluation.silver_set_plan import jobs, units  # importing this reruns the plan and prints its counts

load_dotenv()   # copies the variables in .env (GEMINI_API_KEY) into the environment

MODEL = "gemini-3.5-flash-lite"   # Stable per aistudio.google.com/docs/models (checked 2026-11-23); gemini-2.5-flash is deprecated
JOBS_PER_TYPE = 2           # how many jobs to try for each chunk type (spread evenly over that type's jobs)
SECONDS_BETWEEN_CALLS = 5    # keeps us under the free-tier requests-per-minute limit
MAX_TRIES = 5
LOG_PATH = Path(__file__).resolve().parent / "out" / "silver_try_log.jsonl"

SYSTEM_PROMPT = """You write search questions for a Q&A test set about HIQA inspection reports (Irish nursing homes and disability centres).
You get a passage (its first line is a header with the centre, county, date and, where relevant, the regulation, judgment, risk rating or due date) plus facts about it. Write ONE question that this passage answers.
Rules:
- The question must contain the centre name and the year.
- "Intent" says what the question asks about. "Style" says only how it is worded; it never changes what is asked.
- Pick ONE concrete fact that is specific to this centre (a number, an event, a decision, a concern, a judgment). Ignore generic boilerplate.
- The question must make sense to someone who has not read the report, and must name its specific subject. Never write a vague question such as "what did the centre do about this?".
- Mention a regulation only if the Facts say the passage is about one, and then use exactly that number. For a compliance plan item always include the regulation number with its sub-paragraph, for example 15(1). Never mention a regulation number that is not in the Facts.
- Word it the way the given persona would ask it.
- Do not copy phrases of 4 or more words from the passage.
- Do not say "the passage", "the report says" or "according to".
- The question must be answerable from the passage alone (the header line counts as part of the passage).
- evidence_quote: copy, word for word, the one or two sentences (or the header line) from the passage that answer the question."""

# Style = wording only. Two groups: chunks about a regulation, and chunks with no regulation.
REGULATION_TYPES = {ChunkType.FINDING, ChunkType.PROVIDER_RESPONSE, ChunkType.COMPLIANCE_ITEM}
STYLE_TEXT = {
    ("keyword", True): "Wording only: use the regulation number or the key words of the regulation title, the way someone typing into a search box would.",
    ("paraphrase", True): "Wording only: describe the topic in everyday words instead of the regulation title (for example 'enough staff at night'), but still name the specific topic.",
    ("keyword", False): "Wording only: use specific words that appear in the passage (names, numbers, terms). Do not mention any regulation.",
    ("paraphrase", False): "Wording only: use everyday words instead of the passage's own words, but still name the specific subject. Do not mention any regulation.",
}

NARRATIVE_TOPIC = {
    "what_residents_told_us": "what residents told inspectors and what inspectors observed",
    "capacity_intro": "the capacity and capability overview",
    "quality_intro": "the quality and safety overview",
}


def topic_for(unit: Unit) -> str:
    """One short phrase saying what the passage is about, built from metadata."""
    number = unit.regulation_key.split("-", 1)[1] if "-" in unit.regulation_key else ""
    regulation = f"Regulation {number}: {unit.regulation_title or ''}".strip()
    match unit.chunk_type:
        case ChunkType.FINDING:
            return f"the inspectors' finding on {regulation} (judgment: {unit.judgment.value if unit.judgment else 'n/a'})"
        case ChunkType.PROVIDER_RESPONSE:
            return f"the provider's response to {regulation}"
        case ChunkType.COMPLIANCE_ITEM:
            return f"a compliance plan item for {regulation}"
        case ChunkType.SUMMARY:
            return "the overall inspection summary"
        case ChunkType.ABOUT:
            return "the description of the designated centre"
        case ChunkType.NARRATIVE:
            return NARRATIVE_TOPIC[unit.regulation_key]


def passage_for(unit: Unit) -> str:
    """What the LLM sees as the passage: the header line plus the text, i.e. the same as embed_text."""
    return f"{unit.header}\n{unit.text}"


def build_prompt(job: Job, unit: Unit) -> str:
    place = f"{unit.centre_name} ({unit.county})" if unit.county else unit.centre_name
    style_text = STYLE_TEXT[(job.style, unit.chunk_type in REGULATION_TYPES)]
    return (
        f"Persona: {job.persona}\n"
        f"Intent: {INTENTS[unit.chunk_type][job.intent]}\n"
        f"Style: {style_text}\n"
        f"Facts: centre = {place}; year = {unit.year}; topic = {topic_for(unit)}\n"
        f"Passage:\n{passage_for(unit)}"
    )


class QuotaExceeded(Exception):
    """Gemini answered 429 (a rate limit or the daily quota is used up). Callers should stop."""


def generate_question(client: genai.Client, user_prompt: str) -> tuple[LlmOutput | None, str | None, list[str], dict | None]:
    """Call Gemini. Retry with a growing wait.
    Return (output, raw response text, one message per failed attempt, token usage); output is None if every try fails.
    Raise QuotaExceeded on a 429 (no retry: retrying would only spend more quota)."""
    error_log: list[str] = []
    raw = None
    for attempt in range(MAX_TRIES):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=LlmOutput,
                    temperature=0.7,
                ),
            )
            raw = response.text
            meta = response.usage_metadata
            usage = None if meta is None else {
                "prompt_tokens": meta.prompt_token_count,
                "output_tokens": meta.candidates_token_count,
                "total_tokens": meta.total_token_count,
            }
            return LlmOutput.model_validate_json(raw), raw, error_log, usage
        except (errors.APIError, ValidationError) as e:
            if isinstance(e, errors.APIError) and e.code == 429:
                raise QuotaExceeded(str(e)) from e
            error_log.append(f"attempt {attempt + 1}: {type(e).__name__}: {e}")
            print(f"   attempt {attempt + 1} failed ({type(e).__name__})")
            if attempt < MAX_TRIES - 1:        # no point waiting after the last try
                time.sleep(2 ** (attempt + 1))
    return None, raw, error_log, None


def squash(text: str) -> str:
    """Collapse all whitespace runs to one space, so line breaks do not make an honest quote fail."""
    return " ".join(text.split())


def regulation_numbers(text: str) -> list[str]:
    """Base regulation numbers mentioned in text: 'Regulation 15(1)' and 'Reg. 15' both give '15'."""
    found = re.findall(r"\bReg(?:ulation)?s?\.?\s*(\d+)", text, flags=re.IGNORECASE)
    return sorted({str(int(number)) for number in found})   # int() drops a leading zero: the header prints "08(5)"


def check_output(unit: Unit, output: LlmOutput) -> dict:
    """Mechanical checks on one generated question. Every value is True/False or a list, so the log can be filtered."""
    passage = squash(passage_for(unit))
    quote = squash(output.evidence_quote)
    question = output.eval_ques
    in_question = regulation_numbers(question)
    in_passage = regulation_numbers(passage_for(unit))
    return {
        "quote_in_passage": quote in passage,        # quote is a real copy (header counts)
        "quote_in_text_only": quote in squash(unit.text),   # False + True above = the answer lives only in the header
        "quote_words": len(quote.split()),
        "year_in_question": str(unit.year) in question,
        "centre_in_question": unit.centre_name.lower() in question.lower(),
        "regulations_in_question": in_question,
        "regulations_in_passage": in_passage,
        "invented_regulations": [r for r in in_question if r not in in_passage],   # in the question, nowhere in the passage
        "question_words": len(question.split()),
    }


def log_row(run_id: str, job: Job, unit: Unit, user_prompt: str, output: LlmOutput | None,
            raw: str | None, error: str | None, checks: dict | None, seconds: float) -> None:
    """Append one JSON line with everything needed to debug this question later."""
    row = {
        "run_id": run_id,
        "model": MODEL,
        "job": job.model_dump(),
        "unit": unit.model_dump(mode="json", exclude={"text"}),    # all metadata; text is stored once below as passage
        "passage": passage_for(unit),
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "raw_response": raw,
        "question": output.eval_ques if output else None,
        "evidence_quote": output.evidence_quote if output else None,
        "checks": checks,
        "error": error,
        "seconds": round(seconds, 2),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sample_jobs() -> list[Job]:
    """JOBS_PER_TYPE random jobs of each chunk type (fixed seed, so reruns pick the same ones)."""
    rng = random.Random(0)
    by_type: dict[ChunkType, list[Job]] = {}
    for job in jobs:
        by_type.setdefault(units[job.unit_key].chunk_type, []).append(job)
    picked: list[Job] = []
    for type_jobs in by_type.values():
        picked.extend(rng.sample(type_jobs, JOBS_PER_TYPE))
    return picked


def main() -> None:
    client = genai.Client()   # reads GEMINI_API_KEY from the environment
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for job in sample_jobs():
        unit = units[job.unit_key]
        print("=" * 80)
        print(f"{unit.chunk_type.value} | persona: {job.persona} | intent: {job.intent} | style: {job.style}")
        print(f"{unit.centre_name}, {unit.year} | topic: {topic_for(unit)}")
        user_prompt = build_prompt(job, unit)
        started = time.time()
        output, raw, error_log, _usage = generate_question(client, user_prompt)
        checks = check_output(unit, output) if output else None
        log_row(run_id, job, unit, user_prompt, output, raw, " | ".join(error_log) or None, checks, time.time() - started)
        if output is None:
            print("   FAILED: no output")
        else:
            print(f"Q: {output.eval_ques}")
            print(f"Quote: {output.evidence_quote}")
            print(f"   {checks}")
        time.sleep(SECONDS_BETWEEN_CALLS)
    print(f"\nLog: {LOG_PATH} (run_id {run_id})")


if __name__ == "__main__":
    main()
