# Section heading lines, as regexes to compile with re.MULTILINE. The "1. Capacity and capability of the service:"
# line in "How we inspect" does not match: these must be the whole line.
CAPACITY_HEADING = r"^Capacity and capability[ \t]*$"
QUALITY_HEADING = r"^Quality and safety[ \t]*$"
APPENDIX_HEADING = r"^Appendix 1 -"  # "Appendix 1." also wraps onto a line start inside "How we inspect"
COMPLIANCE_PLAN_HEADING = r"^Compliance Plan for"  # only present when a regulation is not fully compliant
