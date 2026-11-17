import os
from functools import lru_cache

from tokenizers import Tokenizer

# swappable: set EMBEDDING_MODEL to change the tokenizer the chunker counts with
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")


@lru_cache(maxsize=1)
def _tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(EMBEDDING_MODEL)


def count_tokens(text: str) -> int:
    """Token count with the embedding model's own tokenizer (special tokens included, as the model sees them)."""
    return len(_tokenizer().encode(text).ids)
