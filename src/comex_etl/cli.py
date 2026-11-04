"""Command line: ``comex-etl run`` and ``comex-etl sample``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run
from .report import summary
from .sample import generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comex-etl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Clean, cost, load and report a folder of exports")
    p_run.add_argument("--input", type=Path, default=Path("data/sample"))
    p_run.add_argument("--db", type=Path, default=Path("out/comex.db"))
    p_run.add_argument("--report", type=Path, default=Path("out/import_report.xlsx"))

    p_sample = sub.add_parser("sample", help="Regenerate the fictional sample data")
    p_sample.add_argument("--out", type=Path, default=Path("data/sample"))
    p_sample.add_argument("--seed", type=int, default=42)

    args = parser.parse_args(argv)
    if args.command == "sample":
        generate(args.out, seed=args.seed)
        print(f"Sample data written to {args.out}")
        return 0

    result = run(args.input, args.db, args.report)
    print(summary(args.db).to_string(index=False))
    if result.rejected:
        by_rule = result.issues.query("severity == 'reject'")["rule"].value_counts()
        print("\nRejected rows by rule:")
        print(by_rule.to_string())
    print(f"\nDatabase: {args.db}\nReport:   {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
