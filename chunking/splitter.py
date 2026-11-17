from langchain_text_splitters import RecursiveCharacterTextSplitter

from chunking.tokens import count_tokens

MAX_TOKENS = 400  # leaves room for the header under bge-large's 512-token limit
OVERLAP_TOKENS = 50

# paragraph, line, sentence, word: tries the coarsest boundary that fits first
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def split_text(text: str, max_tokens: int = MAX_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Return [text] if it fits the budget, else token-budgeted parts split at sentence boundaries with overlap."""
    if count_tokens(text) <= max_tokens:
        return [text]
    splitter = RecursiveCharacterTextSplitter(
        separators=_SEPARATORS,
        keep_separator="end",  # the full stop stays with its sentence, not the start of the next part
        chunk_size=max_tokens,
        chunk_overlap=overlap,
        length_function=count_tokens,
    )
    return splitter.split_text(text)
