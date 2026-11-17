from chunking.ids import chunk_id, content_hash
from chunking.models import ChunkType


def test_chunk_id_with_key() -> None:
    assert chunk_id("MON-0012345", ChunkType.FINDING, "care-14", 0) == "MON-0012345:finding:care-14:0"


def test_chunk_id_without_key() -> None:
    assert chunk_id("MON-0012345", ChunkType.SUMMARY) == "MON-0012345:summary:0"


def test_chunk_id_part_changes_id() -> None:
    assert chunk_id("MON-1", ChunkType.NARRATIVE, "what_residents_told_us", 1) != chunk_id(
        "MON-1", ChunkType.NARRATIVE, "what_residents_told_us", 0
    )


def test_content_hash_is_stable_and_text_sensitive() -> None:
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
