from pathlib import Path

from ingestion.models import ParsedReport
from chunking.builders import build_chunks
from chunking.country_extracter import extract_county

IN_PATH = Path("data/parsed/reports_narr.jsonl")
OUT_PATH = Path("data/chunks/chunks.jsonl")

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)  # create data/chunks/ if missing

total = 0
with open(IN_PATH, encoding="utf-8") as src, open(OUT_PATH, "w", encoding="utf-8") as out:
    for line in src:
        report = ParsedReport.model_validate_json(line)
        for chunk in build_chunks(report):
            out.write(chunk.model_dump_json() + "\n")
            total += 1

print(f"{total} chunks -> {OUT_PATH}")