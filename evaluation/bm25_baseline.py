"""BM25 keyword baseline on the silver set: no embeddings, no metadata filters.

Run:  uv run python -m evaluation.bm25_baseline
Recall@k here is a hit rate: a question counts if ANY of its labels is in the top k chunks.
Writes evaluation/out/bm25_ranks.json (rank of the first correct chunk per question, null if not in the top 200).
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.jsonl"
SILVER_PATH = ROOT / "evaluation" / "data" / "silver.jsonl"
RANKS_PATH = ROOT / "evaluation" / "out" / "bm25_ranks.json"

K1 = 1.2       # how quickly repeats of a word stop adding score
B = 0.75       # how strongly long chunks are penalised (0 = not at all, 1 = fully)
DEPTH = 200    # how far down the ranking we look for a correct chunk


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class BM25:
    def __init__(self, texts: list[str]) -> None:
        docs = [tokenize(t) for t in texts]
        self.lengths = [len(d) for d in docs]
        self.avg_length = sum(self.lengths) / len(docs)
        self.term_counts = [Counter(d) for d in docs]              # per chunk: word -> times it appears
        self.doc_freq = Counter(w for d in docs for w in set(d))   # word -> number of chunks containing it

    def idf(self, word: str) -> float:
        n, df = len(self.lengths), self.doc_freq[word]
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def term_score(self, word: str, i: int) -> float:
        """What one question word adds to the score of chunk i."""
        tf = self.term_counts[i][word]
        if tf == 0:
            return 0.0
        length_norm = 1 - B + B * self.lengths[i] / self.avg_length
        return self.idf(word) * tf * (K1 + 1) / (tf + K1 * length_norm)

    def rank(self, question: str) -> list[int]:
        """Chunk positions, best first."""
        words = set(tokenize(question))
        scores = [sum(self.term_score(w, i) for w in words) for i in range(len(self.lengths))]
        return sorted(range(len(scores)), key=lambda i: -scores[i])


def base_key(chunk_id: str) -> str:
    return chunk_id.rsplit(":", 1)[0]   # drop the part number


def first_hit(order: list[int], chunk_ids: list[str], gold: set[str]) -> int | None:
    for position, i in enumerate(order[:DEPTH], 1):
        if base_key(chunk_ids[i]) in gold:
            return position
    return None


def recall_at(ranks: list[int | None], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def main() -> None:
    chunks = read_jsonl(CHUNKS_PATH)
    questions = read_jsonl(SILVER_PATH)
    chunk_ids = [c["chunk_id"] for c in chunks]
    index = BM25([c["embed_text"] for c in chunks])

    ranks: dict[str, int | None] = {}
    by_type: dict[str, list[int | None]] = defaultdict(list)
    for q in questions:
        rank = first_hit(index.rank(q["question"]), chunk_ids, set(q["label"]))
        ranks[q["question_id"]] = rank
        by_type[q["chunk_type"]].append(rank)

    all_ranks = list(ranks.values())
    print(f"{len(all_ranks)} questions, {len(chunks)} chunks")
    for k in (1, 5, 10, 50):
        print(f"Recall@{k}: {recall_at(all_ranks, k):.3f}")
    print("\nRecall@5 by chunk type")
    for chunk_type, type_ranks in by_type.items():
        print(f"  {chunk_type:18} n={len(type_ranks):3}  {recall_at(type_ranks, 5):.2f}")
    print(f"Average of the per-type scores: {sum(recall_at(r, 5) for r in by_type.values()) / len(by_type):.3f}")

    RANKS_PATH.write_text(json.dumps(ranks, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
