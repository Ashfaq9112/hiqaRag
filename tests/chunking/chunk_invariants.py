"""Checks that every chunk in chunks.jsonl is well formed. Used by test_chunk_invariants.py.

A violation is a pair (chunk_id, check_name), so an accepted exception is one small tuple.
"""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from chunking.models import Chunk, ChunkType

DEFAULT_CHUNKS = Path("data/chunks/chunks.jsonl")
MAX_TOKENS = 512  # bge-large limit: more than this is silently truncated
MIN_TOKENS = 20

Violation = tuple[str, str]

REGULATION_FIELDS = ("series", "regulation_number", "regulation_title")


def load_chunks(path: Path = DEFAULT_CHUNKS) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        return [Chunk.model_validate_json(line) for line in f]


def judgment_words(c: Chunk) -> str:
    return c.judgment.value.replace("_", " ").capitalize()  # "not_compliant" -> "Not compliant"


@dataclass(frozen=True)
class Rule:
    required: tuple[str, ...]  # fields that must not be None
    forbidden: tuple[str, ...]  # fields that must be None
    header_phrases: Callable[[Chunk], list[str]]  # text the header must contain
    key_ok: Callable[[Chunk, str], bool]  # is the key part of chunk_id right? ("" = no key)


NO_REGULATION = REGULATION_FIELDS + ("judgment", "risk_rating")

RULES: dict[ChunkType, Rule] = {
    ChunkType.FINDING: Rule(
        required=REGULATION_FIELDS + ("dimension", "judgment"),
        forbidden=("risk_rating",),
        header_phrases=lambda c: [f"Regulation {c.regulation_number}: {c.regulation_title}. {judgment_words(c)}."],
        key_ok=lambda c, key: key == f"{c.series.value}-{c.regulation_number}",
    ),
    ChunkType.PROVIDER_RESPONSE: Rule(
        required=REGULATION_FIELDS + ("judgment",),  # dimension is borrowed from the finding, may be missing
        forbidden=("risk_rating",),
        header_phrases=lambda c: [f"Provider's response to Regulation {c.regulation_number}: {c.regulation_title}."],
        key_ok=lambda c, key: key == f"{c.series.value}-{c.regulation_number}",
    ),
    ChunkType.COMPLIANCE_ITEM: Rule(
        required=("judgment", "risk_rating"),  # regulation fields are None when no finding matched
        forbidden=(),
        header_phrases=lambda c: ["Compliance plan,", f"Risk rating: {c.risk_rating.value}."],
        key_ok=lambda c, key: key.startswith(("care-", "registration-")),
    ),
    ChunkType.SUMMARY: Rule(
        required=(),
        forbidden=NO_REGULATION + ("dimension",),
        header_phrases=lambda c: ["Inspection summary."],
        key_ok=lambda c, key: key == "",
    ),
    ChunkType.ABOUT: Rule(
        required=(),
        forbidden=NO_REGULATION + ("dimension",),
        header_phrases=lambda c: ["About the centre."],
        key_ok=lambda c, key: key == "",
    ),
    ChunkType.NARRATIVE: Rule(
        required=(),
        forbidden=NO_REGULATION,
        header_phrases=lambda c: [NARRATIVE_LABELS.get(c.chunk_id.split(":")[2], "<unknown narrative key>")],
        key_ok=lambda c, key: key in NARRATIVE_LABELS,
    ),
}

NARRATIVE_LABELS = {
    "what_residents_told_us": "What residents told inspectors and what inspectors observed.",
    "capacity_intro": "Capacity and capability overview.",
    "quality_intro": "Quality and safety overview.",
}


def split_id(c: Chunk) -> tuple[list[str], str]:
    """chunk_id 'MON-1:finding:care-14:0' -> (['MON-1', 'finding', 'care-14', '0'], 'care-14'). Key is '' if absent."""
    parts = c.chunk_id.split(":")
    key = parts[2] if len(parts) == 4 else ""
    return parts, key


def check_chunk(c: Chunk) -> list[Violation]:
    found: list[Violation] = []

    def bad(check: str) -> None:
        found.append((c.chunk_id, check))

    # --- layer 1: every chunk ---
    if c.token_count > MAX_TOKENS:
        bad("too_long")
    if c.token_count < MIN_TOKENS:
        bad("too_short")
    if not c.display_text.strip():
        bad("empty_display_text")

    parts, key = split_id(c)
    if len(parts) not in (3, 4) or parts[0] != c.report_id or parts[1] != c.chunk_type.value or parts[-1] != str(c.part):
        bad("chunk_id_malformed")

    suffix = "\n" + c.display_text
    header = c.embed_text[: -len(suffix)] if c.embed_text.endswith(suffix) else None
    if header is None:
        bad("embed_text_is_not_header_plus_display_text")
    else:
        d = c.inspection_date
        if not header.strip():
            bad("empty_header")
        if not header.startswith(c.centre_name):
            bad("header_does_not_start_with_centre_name")
        if f"{d.day} {d:%B %Y}" not in header:
            bad("header_missing_date")
        if "None" in header:
            bad("header_contains_None")

    # --- layer 2: per-type table ---
    rule = RULES[c.chunk_type]
    for field in rule.required:
        if getattr(c, field) is None:
            bad(f"missing_{field}")
    for field in rule.forbidden:
        if getattr(c, field) is not None:
            bad(f"unexpected_{field}")
    if not rule.key_ok(c, key):
        bad("chunk_id_key_wrong_for_type")
    if header is not None and not any(getattr(c, f) is None for f in rule.required):
        for phrase in rule.header_phrases(c):
            if phrase not in header:
                bad(f"header_missing:{phrase}")
    return found


def check_groups(chunks: list[Chunk]) -> list[Violation]:
    """Layer 3: ids are unique; the parts of one split text are 0..n-1 and agree on their metadata."""
    found: list[Violation] = []

    seen: set[str] = set()
    for c in chunks:
        if c.chunk_id in seen:
            found.append((c.chunk_id, "duplicate_chunk_id"))
        seen.add(c.chunk_id)

    groups: dict[tuple[str, str, str], list[Chunk]] = defaultdict(list)
    for c in chunks:
        groups[(c.report_id, c.chunk_type.value, split_id(c)[1])].append(c)

    for (report_id, chunk_type, key), members in groups.items():
        label = ":".join(p for p in (report_id, chunk_type, key) if p)
        if sorted(m.part for m in members) != list(range(len(members))):
            found.append((label, "parts_not_0_to_n_minus_1"))
        for field in REGULATION_FIELDS + ("judgment", "dimension"):
            if len({getattr(m, field) for m in members}) > 1:
                found.append((label, f"parts_disagree_on_{field}"))
    return found


def all_violations(chunks: list[Chunk]) -> list[Violation]:
    found = check_groups(chunks)
    for c in chunks:
        found.extend(check_chunk(c))
    return found


# accepted violations: (chunk_id, check). All 7 checked against the PDFs on 2026-11-20: the source data is the problem.
KNOWN_EXCEPTIONS: set[Violation] = {
    # compliant regulations with no text under them in the PDF (5 findings; 2 of them also fall under 20 tokens)
    ("MON-0037953:finding:care-22:0", "empty_display_text"),
    ("MON-0032474:finding:care-3:0", "empty_display_text"),
    ("MON-0042096:finding:care-29:0", "empty_display_text"),
    ("MON-0033691:finding:care-18:0", "empty_display_text"),
    ("MON-0045181:finding:care-3:0", "empty_display_text"),
    # Section 2 row has no risk rating in the PDF (2 compliance items)
    ("MON-0040067:compliance_item:care-23(2)(b):0", "missing_risk_rating"),
    ("MON-0044126:compliance_item:care-7(3):0", "missing_risk_rating"),
}
