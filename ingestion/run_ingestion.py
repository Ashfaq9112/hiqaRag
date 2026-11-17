import argparse
from collections import Counter
from pathlib import Path

from ingestion.assemble import SKIPPED_KINDS, parse_report
from ingestion.classifier import ReportKind

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_ingestion(root: Path, out_path: Path) -> None:
    """Parse every PDF under root, write one ParsedReport per line (JSON Lines) and report counts per kind."""
    pdfs = sorted(root.rglob("*.pdf"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    counts: Counter[ReportKind] = Counter()
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []
    with out_path.open("w", encoding="utf-8") as handle:
        for i, pdf in enumerate(pdfs, start=1):
            relative = pdf.relative_to(root).as_posix()
            print(f"[{i}/{len(pdfs)}] {relative}")
            try:
                kind, report = parse_report(pdf, source_file=relative)
            except Exception as error:  # one bad PDF must not stop the batch
                print(f"  FAILED: {error}")
                failed.append((relative, str(error)))
                continue
            counts[kind] += 1
            if report is None:
                skipped.append(f"{kind.value}\t{relative}")
                continue
            handle.write(report.model_dump_json() + "\n")

    skipped_path = out_path.with_name("skipped.txt")
    lines = skipped + [f"failed\t{path}\t{error}" for path, error in failed]
    skipped_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"\nDone: {len(pdfs)} PDFs -> {out_path}")
    for kind in ReportKind:
        status = "skipped" if kind in SKIPPED_KINDS else "parsed"
        print(f"  {kind.value:<22}{counts[kind]:>5}  {status}")
    print(f"  {'failed':<22}{len(failed):>5}")
    print(f"Skipped and failed files listed in {skipped_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "data/raw/samples")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "data/parsed/reports.jsonl")
    args = parser.parse_args()
    run_ingestion(args.root, args.out)


if __name__ == "__main__":
    main()
