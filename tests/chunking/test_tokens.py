from chunking.tokens import count_tokens


def test_count_tokens_grows_with_text() -> None:
    short = count_tokens("Regulation 14: Persons in charge.")
    long = count_tokens("Regulation 14: Persons in charge. " * 10)
    assert 0 < short < long
