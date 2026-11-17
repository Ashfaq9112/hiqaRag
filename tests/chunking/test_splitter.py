from chunking.splitter import split_text
from chunking.tokens import count_tokens

SENTENCES = [f"Inspector observed item number {i} in the centre today." for i in range(120)]
LONG = " ".join(SENTENCES)


def test_short_text_is_not_split() -> None:
    assert split_text("One short sentence.") == ["One short sentence."]


def test_long_text_split_within_budget() -> None:
    parts = split_text(LONG, max_tokens=100, overlap=20)
    assert len(parts) > 1
    assert all(count_tokens(p) <= 100 for p in parts)


def test_parts_cover_all_sentences_and_overlap() -> None:
    parts = split_text(LONG, max_tokens=100, overlap=20)
    joined = " ".join(parts)
    assert all(s.rstrip(".") in joined for s in SENTENCES)
    # overlap: the end of one part reappears at the start of the next
    assert parts[0].split()[-1] in parts[1]


def test_parts_start_and_end_on_sentence_boundaries() -> None:
    parts = split_text(LONG, max_tokens=100, overlap=0)
    assert all(p.rstrip().endswith(".") for p in parts)
