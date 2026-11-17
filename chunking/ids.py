
import hashlib

from chunking.models import ChunkType


def chunk_id(report_id: str, chunk_type: ChunkType, key: str = "", part: int = 0) -> str:
    """Readable, deterministic ID, e.g. 'MON-0012345:finding:care-14:0'. `key` is empty when the type has one chunk per report."""
    parts = [report_id, chunk_type.value, key, str(part)]
    return ":".join(p for p in parts if p)


def content_hash(embed_text: str) -> str:
    return hashlib.sha256(embed_text.encode("utf-8")).hexdigest()
