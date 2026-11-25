"""Generate the silver question set, one question per job. Safe to stop and rerun: it skips jobs already logged.

Run:  uv run python -m evaluation.silver_generate
Stops by itself on the first 429 (quota); just run it again later and it carries on.

Files in evaluation/out/:
  silver.jsonl        clean eval set: accepted questions only, with their label
  silver_debug.jsonl  one row per job (accepted, rejected or failed) with everything needed to debug it
  silver_runs.jsonl   one summary line per run
"""
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from google import genai

from evaluation.model import QUOTAS, Job, LlmOutput, Unit
from evaluation.silver_set_plan import jobs, label_index, units
from evaluation.silver_try import (  # importing silver_try also loads .env (GEMINI_API_KEY)
    MODEL, SECONDS_BETWEEN_CALLS, SYSTEM_PROMPT, QuotaExceeded,
    build_prompt, check_output, generate_question, passage_for,
)

OUT_DIR = Path(__file__).resolve().parent / "out"
CLEAN_PATH = OUT_DIR / "silver.jsonl"
DEBUG_PATH = OUT_DIR / "silver_debug.jsonl"
RUNS_PATH = OUT_DIR / "silver_runs.jsonl"
TEMPERATURE = 0.7   # same value as in generate_question


def read_rows(path: Path) -> list[dict]:
    """All rows of a JSONL file. A missing file gives []. A half-written last line (crash) is skipped."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_row(path: Path, row: dict) -> None:
    """Append one JSON line. The with-block closes (and so flushes) the file, so a crash loses at most the row being written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.exists() and path.stat().st_size > 0:
        with open(path, "rb") as f:
            f.seek(-1, 2)                       # last byte of the file
            if f.read(1) != b"\n":              # a crash left a half line: start a new line so it cannot swallow this row
                prefix = "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + json.dumps(row, ensure_ascii=False) + "\n")


def label_for(unit: Unit) -> list[str]:
    """Every base key that is a correct answer for this unit: same centre, year, chunk type and regulation."""
    return label_index[(unit.centre_id, unit.year, unit.chunk_type, unit.regulation_key)]


def reject_reasons(unit: Unit, checks: dict, label: list[str]) -> list[str]:
    """Why a generated question must be thrown away. Empty list means accepted."""
    reasons: list[str] = []
    if not checks["quote_in_passage"]:
        reasons.append("quote_not_in_passage")
    if not checks["centre_in_question"]:
        reasons.append("centre_not_in_question")
    if not checks["year_in_question"]:
        reasons.append("year_not_in_question")
    if checks["invented_regulations"]:
        reasons.append("invented_regulation")
    if unit.base_key not in label:
        reasons.append("source_not_in_label")
    return reasons


def make_rows(run_id: str, job: Job, unit: Unit, user_prompt: str, output: LlmOutput | None, raw: str | None,
              error_log: list[str], usage: dict | None, seconds: float) -> tuple[dict, dict | None]:
    """Build (debug row, clean row). The clean row is None unless the question is accepted."""
    label = label_for(unit)
    checks = check_output(unit, output) if output else None
    reasons = reject_reasons(unit, checks, label) if output else []
    status = "failed" if output is None else ("rejected" if reasons else "accepted")

    debug = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "reject_reasons": reasons,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "job": job.model_dump(),
        "unit": unit.model_dump(mode="json", exclude={"text"}),   # all metadata; the text is stored once as passage
        "passage": passage_for(unit),
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "raw_response": raw,
        "question": output.eval_ques if output else None,
        "evidence_quote": output.evidence_quote if output else None,
        "checks": checks,
        "label": label,
        "attempt_errors": error_log,
        "usage": usage,
        "seconds": round(seconds, 2),
    }
    clean = None
    if status == "accepted":
        clean = {
            "question_id": unit.base_key,
            "question": output.eval_ques,
            "label": label,
            "chunk_type": unit.chunk_type.value,
            "intent": job.intent,
            "persona": job.persona,
            "style": job.style,
            "expected_filters": {
                "service_type": unit.service_type.value,
                "county": unit.county,
                "centre_id": unit.centre_id,
                "year": unit.year,
                "regulation": unit.regulation_key or None,
                "judgment": unit.judgment.value if unit.judgment else None,
            },
            "source": "silver",
        }
    return debug, clean


def write_rows(debug: dict, clean: dict | None) -> None:
    append_row(DEBUG_PATH, debug)
    if clean:
        append_row(CLEAN_PATH, clean)


def summarise(run_id: str, this_run: list[dict], stopped_by: str) -> None:
    """Print and store a summary of this run, plus how far each chunk type is from its quota."""
    status = Counter(r["status"] for r in this_run)
    reasons = Counter(reason for r in this_run for reason in r["reject_reasons"])
    tokens = sum((r["usage"] or {}).get("total_tokens") or 0 for r in this_run)
    calls = sum(len(r["attempt_errors"]) + (r["status"] != "failed") for r in this_run)
    accepted_by_type = Counter(r["unit"]["chunk_type"] for r in read_rows(DEBUG_PATH) if r["status"] == "accepted")
    progress = {t.value: f"{accepted_by_type[t.value]}/{quota}" for t, quota in QUOTAS.items()}
    summary = {
        "run_id": run_id, "stopped_by": stopped_by, "jobs_this_run": len(this_run), "status": dict(status),
        "reject_reasons": dict(reasons), "total_tokens": tokens, "api_calls": calls, "accepted_vs_quota": progress,
    }
    print("\n" + "=" * 80)
    for key, value in summary.items():
        print(f"{key}: {value}")
    append_row(RUNS_PATH, summary)


def main() -> None:
    client = genai.Client()   # reads GEMINI_API_KEY from the environment
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    done = {r["job"]["unit_key"] for r in read_rows(DEBUG_PATH) if r["status"] in ("accepted", "rejected")}
    todo = [job for job in jobs if job.unit_key not in done]
    print(f"{len(jobs)} jobs in the plan, {len(done)} already done, {len(todo)} to run")

    this_run: list[dict] = []
    stopped_by = "finished"
    try:
        for n, job in enumerate(todo, 1):
            unit = units[job.unit_key]
            user_prompt = build_prompt(job, unit)
            started = time.time()
            output, raw, error_log, usage = generate_question(client, user_prompt)
            debug, clean = make_rows(run_id, job, unit, user_prompt, output, raw, error_log, usage, time.time() - started)
            write_rows(debug, clean)
            this_run.append(debug)
            print(f"[{n}/{len(todo)}] {unit.chunk_type.value} {job.intent}: {debug['status']} {debug['reject_reasons'] or ''}")
            if n < len(todo):
                time.sleep(SECONDS_BETWEEN_CALLS)
    except QuotaExceeded as e:
        stopped_by = f"429 quota: {str(e)[:200]}"
        print(f"\nSTOPPED: Gemini returned 429. Run again later to resume.\n{e}")
    except KeyboardInterrupt:
        stopped_by = "ctrl+c"
    finally:
        summarise(run_id, this_run, stopped_by)


if __name__ == "__main__":
    main()
