from enum import StrEnum


class ReportKind(StrEnum):
    NURSING_HOME = "nursing_home"
    DISABILITY_ADULTS = "disability_adults"
    DISABILITY_CHILDREN = "disability_children"
    DISABILITY_MIXED = "disability_mixed"
    THEMATIC = "thematic"
    UNKNOWN = "unknown"


def classify_report(cover_text: str) -> ReportKind:
    text = " ".join(cover_text.lower().split())  # collapse wrapped lines

    if "thematic inspection" in text:  # must come first: its title also contains "older people"
        return ReportKind.THEMATIC
    if "designated centre for older people" in text:
        return ReportKind.NURSING_HOME
    if "designated centre for disabilities" in text:
        if "(children)" in text:
            return ReportKind.DISABILITY_CHILDREN
        if "(adults)" in text:
            return ReportKind.DISABILITY_ADULTS
        if "(mixed)" in text:
            return ReportKind.DISABILITY_MIXED
    return ReportKind.UNKNOWN
