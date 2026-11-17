# Lessons learned — HIQA RAG

Obstacles hit while building the ingestion pipeline, and how each was overcome. Newest last.

## 1. Bot verification on hiqa.ie

- **Obstacle:** both the report listing and the PDF host answer scripted requests with `503 Service Unavailable`
  and a `botbuster_token` cookie. A plain download script only ever received the challenge page.
- **How it was overcome:** no automation around the check. `robots.txt` allows the report pages, but the
  verification is a stricter signal, so it was respected. Report links were collected from the user's own
  browser session with a small DevTools snippet (a page the user had loaded and verified) and the PDFs saved
  by hand. A balanced slice (50 reports per service type per year, 2023–2026) was enough to build and
  evaluate the pipeline. Scaling to the full ~7,000 reports needs HIQA's permission for bulk access.

## 2. A template that only looks uniform on 24 samples

- **Obstacle:** parsers were verified on 24 hand-picked PDFs and passed. The first run over 400 real reports
  produced 20 failures, 2 unclassified reports and 9 reports with silently missing data.
- **How it was overcome:** treat the first full run as the real test. Every failure was grouped by cause,
  reproduced as a failing test using the real wording, then fixed (tests first). Final result: 378 parsed,
  22 thematic skipped by design, 0 unknown, 0 failed.

## 3. Variants the samples never showed

| Variant | Symptom | Fix |
|---|---|---|
| Thematic inspections (5.5% of reports) | Different template, no regulations | Detected from the cover title, skipped, and counted per kind in the run summary |
| "Short Notice Announced" inspection type | Enum validation error on 14 reports | Added the value; normalisation joins words with underscores |
| Multi-day inspections ("22 & 29 May 2024", "30 June and 1 July 2024") | Date parsing error on 5 reports | Take the first day, with the month and year from the end of the range |
| "Designated Centre for Disabilities (Mixed)" | Classifier returned `unknown` | New `disability_mixed` kind and service type |
| `Registration Regulation 8 (1)` heading with no colon or title | Parse error in findings; missing row in the appendix | Accept the bare form in both parsers, only with the `Registration` prefix |

## 4. Silent data loss (the worst kind of bug)

- **Obstacle:** the findings parser found the first regulation block of a section only if the preceding line
  ended in `.`, `!` or `?`. Where an intro paragraph ended without punctuation, the whole section returned no
  findings and raised no error. Nine reports were missing 1 to 9 findings each.
- **How it was found:** cross-checking two independent parsers. The Appendix lists every regulation and its
  judgment, so findings and appendix rows must match one-to-one. Nine did not.
- **How it was overcome:** keep the old rule, and only when it finds nothing in a section that does contain
  judgments, fall back to an Appendix-anchored start (the last matching heading before the first judgment,
  which skips prose mentions that wrap onto a line start).
- **Safety net:** before the fix, a snapshot of the output was saved; after it, every record was compared. All
  368 previously correct reports were identical, the 9 broken ones were repaired, and one new report parsed.
  Lesson: a fix to a parser needs a regression diff against the previous output, not only unit tests.

## 5. Smaller pitfalls

- A greedy cover regex (`Fieldwork ID:(.*)`) runs to the end of whatever text it is given, so the cover
  parser is only fed page 1.
- Running a module file by path breaks package imports (`ModuleNotFoundError`); run it as
  `uv run python -m ingestion.run_ingestion`.

## 6. Compliance plan, Section 1: provider responses (bugs A, B, C)

- **Obstacle:** in about 20 reports a provider response was duplicated or lost, and "Outline how you are going to
  come into compliance..." text leaked into response bodies. 2 findings also had empty text.
- **How it was found:** chunking ran cleanly (13,395 chunks, none over budget), so the damage only showed up
  when the numbers were inspected: duplicate (series, regulation) keys, empty bodies, and the "Outline how"
  sentence appearing inside a body.
- **How it was overcome:** the parser now anchors on the "Outline how you are going to..." sentence, because it
  repeats the full regulation title. The heading start is the last `Regulation N:` line before it, the judgment
  is the last judgment line before it, and an empty block with the same key as the next block is skipped.
- **Verified by:** re-parsing all 400 PDFs. Duplicate keys went 4 to 0, "Outline how" inside bodies 5 to 0,
  empty bodies 3 to 0.

## 7. Compliance plan, Section 2: regulation items (bugs D to H)

- **Obstacle:** the text-based parser lost or merged rows. Rows continue across page breaks, column positions
  shift between files, and a regulation ref can be split so that its tail (e.g. `05(6)(c)`) lands on the next
  line. A row's judgment, risk colour and date could end up inside the previous row's requirement text.
- **How it was found:** by chance, while looking at individual reports. Then the old output was compared against
  a new extractor built on `find_tables()` (`tests/compare_items.py`).
- **A wrong guess:** some rows seemed missing, and we first read that as a gap in the source data. It was not:
  those rows were interleaved or split and had been swallowed into the previous item.
- **How it was overcome:** a table-based extractor. It finds the `Section 2:` page, reads the tables page by
  page, and skips header rows. A row whose first cell starts with `Regulation` or `Registration` starts a new
  item, and any other row continues the previous one. Cells are classified by content (judgment words,
  Yellow/Orange/Red, dd/mm/yyyy, the rest is the requirement), never by column index. For the 84 reports with a
  page where no table is detected, the page is read as text and glued onto the previous row. A ref with no digit
  yet takes a tail cell like `05(6)(c)`.
- **Result of the comparison:** 2,136 items identical, 70 rows only in the new output (the old parser had lost
  them), 51 differences (50 were a swallowed neighbour row, 1 a truncation), 3 only in the old (one fake row,
  two refs missing `(a)`/`(b)`). The new parser yields 2,257 rows against 2,190.
- **Accepted trade-off:** `table.extract()` scatters commas inside cells (991 rows, e.g. `residents the , statement`).
  Left as is. The fix would be `page.get_text(clip=cell_bbox)`. The same text feeds embeddings and BM25.
- **Real data gaps (not bugs):** 2 rows have no risk rating, 20 rows in 3 reports have no date.
- **Lesson:** these bugs were found by chance. A corpus-wide check and a diff against the previous run find them
  on purpose (see the test plan).

## 8. Narrative intro swallowing a whole section (bug fixed 2026-11-09)

- **Obstacle:** in 9 reports (6 `capacity_intro`, 3 `quality_intro`) the intro text swallowed the first regulation
  blocks, including `Judgment:` lines. The intro was cut at the first block heading, but a heading was only
  recognised when the intro ended with closing punctuation.
- **How it was found:** the corpus invariant "narrative contains 'Judgment:'", not by reading reports.
- **How it was overcome:** one shared `first_block_start` in `ingestion/parsers/findings.py`, used by both the
  findings parser and `_intro`, so the two can never disagree about where the first block starts. A full rerun of
  400 PDFs diffed against the previous output changed only those 9 fields.
- **Lesson:** two parsers deciding the same boundary independently will drift. Share the rule.

## 9. Accepted violations: HIQA's own documents disagree

- **Obstacle:** after the last parser fix the invariants still showed 11 violations. All 11 were checked in the
  PDFs and are in the source: 9 compliance-plan items say "not compliant" where Appendix 1 says "substantially
  compliant" (6 reports), one US/UK spelling (`behavioral`/`behavioural`), one centre renamed (OSV-0000184).
- **Decision:** do not "fix" them in the parser. They are listed in `KNOWN_EXCEPTIONS`
  (`tests/corpus_invariants.py`) as `(source_file, check, detail)`, so anything beyond them is new.
- **Later impact:** resolve centres by `centre_id`, never by name.

## 10. Making the invariants a gate (pytest)

- **Problem:** the invariant script only printed. Nothing failed if a parser change broke a rule, and someone had
  to remember to run it and compare against the 11 known violations by eye.
- **Fix:** `tests/test_corpus_invariant.py` runs the same checks under pytest: one test per report (Group A), one
  corpus-level test, one slow test per report that re-counts in the PDF, and a stale-exception test so the
  accepted list cannot rot. Any violation not in `KNOWN_EXCEPTIONS` fails the run.
- **Rule of use:** after any parser change, re-run `ingestion.run_ingestion` first (the tests read the JSONL, not
  the code), then `uv run pytest`. The PDF re-count is slow (about 90 s for 378 reports), so it is marked `slow`.
- See `learnings/phase-6-corpus-invariants-pytest.md` for how the tests work.

## Known and deferred

- Bullet glyphs in provider responses appear as `�`.
- Pre-2023 reports are unverified.
