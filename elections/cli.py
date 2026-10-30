import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Brazilian presidential runoff analysis")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("download", help="Download official TSE data with hashes")
    fetch.add_argument("--year", type=int, default=2026)
    fetch.add_argument("--output", default="data/raw/2026")
    prep = sub.add_parser("prepare", help="Validate and normalize official section-level files")
    prep.add_argument("--year", type=int, default=2026)
    prep.add_argument("--raw", default="data/raw/2026")
    prep.add_argument("--output", default="data/processed/2026")
    run = sub.add_parser("analyze", help="Analyze every domestic municipality")
    run.add_argument("--processed", default="data/processed/2026")
    run.add_argument("--output", default="results/2026")
    run.add_argument("--bootstrap", type=int, default=150)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--seed", type=int, default=20261029)
    run.add_argument("--min-sections", type=int, default=10)
    run.add_argument("--municipality", type=int, nargs="+", help="Optional TSE municipality codes")
    timing = sub.add_parser("timing", help="Audit normalized log events against section turnout")
    timing.add_argument("--events", required=True)
    timing.add_argument("--processed", default="data/processed/2026")
    timing.add_argument("--output", default="results/2026/timing")
    timing.add_argument("--round-one-date", required=True, help="YYYY-MM-DD")
    timing.add_argument("--round-two-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    if args.command == "download":
        from .download import download
        print(json.dumps(download(args.year, args.output), indent=2, ensure_ascii=False))
    elif args.command == "prepare":
        from .data import prepare
        print(json.dumps(prepare(args.raw, args.output, args.year), indent=2, ensure_ascii=False))
    elif args.command == "analyze":
        if args.bootstrap < 0 or args.workers < 1 or args.min_sections < 5:
            parser.error("Require bootstrap >= 0, workers >= 1, and min-sections >= 5")
        from .analysis import analyze
        print(json.dumps(analyze(args.processed, args.output, args.bootstrap, args.workers,
                                 args.seed, args.min_sections, args.municipality), indent=2, ensure_ascii=False))
    elif args.command == "timing":
        from pathlib import Path
        import pandas as pd
        from .timing import audit_events
        expected = pd.read_csv(Path(args.processed) / "section_rounds.csv.gz")
        print(json.dumps(audit_events(args.events, expected, args.output,
            {"1": args.round_one_date, "2": args.round_two_date}), indent=2))
