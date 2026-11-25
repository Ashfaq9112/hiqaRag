from evaluation.model import Unit, Job, LlmOutput, QUOTAS, PERSONAS_BY_TYPE, STYLES, INTENTS
from chunking.models import Chunk
from pathlib import Path
from collections import defaultdict, Counter
from itertools import cycle, product, zip_longest, chain, islice
import math
import random
PROJECT_ROOT = Path(__file__).resolve().parent.parent

chunk_path = PROJECT_ROOT /"data"/"chunks"/"chunks.jsonl"


# step 1: group the chunks by base key (chunk_id without the part number)
parts = defaultdict(list)
with open(chunk_path, encoding="utf-8") as f:
    for line in f:
        chunk = Chunk.model_validate_json(line)
        parts[chunk.chunk_id.rsplit(":", 1)[0]].append(chunk)

# step 2: one Unit per base key, and the label index
units: dict[str, Unit] = {}
label_index = defaultdict(list)

for base_key, chunks in parts.items():
    chunks.sort(key=lambda c: c.part)
    first = chunks[0]
    regulation_key = ":".join(first.chunk_id.split(":")[2:-1])  # "care-28", "" for summary/about
    unit = Unit(base_key=base_key, text=" ".join(c.display_text for c in chunks),
                header=first.embed_text.removesuffix(first.display_text).strip(),   # embed_text = header + "\n" + display_text
                token_count=sum(c.token_count for c in chunks), chunk_type=first.chunk_type,
                centre_id=first.centre_id, centre_name=first.centre_name, county=first.county,
                year=first.inspection_date.year, service_type=first.service_type,
                judgment=first.judgment, regulation_key=regulation_key, regulation_title=first.regulation_title)
    units[base_key] = unit
    label_index[(unit.centre_id, unit.year, unit.chunk_type, unit.regulation_key)].append(base_key)

print("units: ", len(units))
print("label_index keys: ", len(label_index))
print("label_index keys with more than 1 base key: ", sum(len(v) > 1 for v in label_index.values()))


MIN_TOKENS = 20
OVER_GENERATE = 1.25


def eligible_units(units: dict[str, Unit]) -> list[Unit]:
    """Drop tiny units and units whose text we have already seen."""
    seen_texts: set[str] = set()
    keep: list[Unit] = []
    for unit in units.values():
        if unit.token_count < MIN_TOKENS or unit.text in seen_texts:
            continue
        seen_texts.add(unit.text)
        keep.append(unit)
    return keep


def draw_units(candidates: list[Unit], target: int, rng: random.Random) -> list[Unit]:
    """Take `target` units, one from each (service_type, judgment) group in turn."""
    groups: dict[tuple, list[Unit]] = defaultdict(list)
    for unit in candidates:
        groups[(unit.service_type, unit.judgment, unit.year)].append(unit)

    group_lists = list(groups.values())
    rng.shuffle(group_lists)          # which group goes first is random too
    for group in group_lists:
        rng.shuffle(group)

    round_robin = chain.from_iterable(zip_longest(*group_lists))   # a1 b1 c1 a2 b2 c2 ...
    return list(islice((u for u in round_robin if u is not None), target))


def make_jobs(units: dict[str, Unit], seed: int = 42) -> list[Job]:
    rng = random.Random(seed)
    candidates = eligible_units(units)
    jobs: list[Job] = []
    for chunk_type, quota in QUOTAS.items():
        of_this_type = [u for u in candidates if u.chunk_type == chunk_type]
        chosen = draw_units(of_this_type, math.ceil(quota * OVER_GENERATE), rng)
        # every (persona, intent, style) combination in turn, so no persona is stuck with one intent
        combos = cycle(product(PERSONAS_BY_TYPE[chunk_type], INTENTS[chunk_type], STYLES))
        for unit in chosen:
            persona, intent, style = next(combos)
            jobs.append(Job(unit_key=unit.base_key, persona=persona, intent=intent, style=style))
    return jobs


jobs = make_jobs(units)
print("jobs: ", len(jobs))
for label, counter in {
    "per chunk type": Counter(units[j.unit_key].chunk_type for j in jobs),
    "per service type": Counter(units[j.unit_key].service_type for j in jobs),
    "per judgment": Counter(units[j.unit_key].judgment for j in jobs),
    "per year": Counter(units[j.unit_key].year for j in jobs),
    "per persona": Counter(j.persona for j in jobs),
    "per style": Counter(j.style for j in jobs),
    "per intent": Counter(j.intent for j in jobs),
}.items():
    print(label, dict(counter))
