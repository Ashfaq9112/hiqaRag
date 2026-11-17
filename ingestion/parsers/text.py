import re

_PAGE_HEADER = re.compile(r"^[ \t]*Page \d+ of \d+[ \t]*$", re.MULTILINE)
# SymbolMT / Wingdings bullets land in the private-use area; some reports use a real "▪" instead
_GLYPH_BULLET = re.compile(r"[-▪]")


def clean_text(pages: list[str]) -> str:
    """Join page texts, drop the 'Page N of M' headers and normalise bullet glyphs. Line breaks are kept."""
    text = _PAGE_HEADER.sub("", "\n".join(pages))
    return _GLYPH_BULLET.sub("•", text)
