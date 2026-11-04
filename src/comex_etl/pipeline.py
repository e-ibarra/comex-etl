"""Extract → validate → cost → load → report, as one function."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .costing import Rates, landed_cost
from .extract import read_all
from .load import load
from .report import write_report
from .validate import validate_lines, validate_shipments


@dataclass
class RunResult:
    costed: pd.DataFrame
    shipments: pd.DataFrame
    issues: pd.DataFrame

    @property
    def rejected(self) -> int:
        return int((self.issues["severity"] == "reject").sum())


def run(input_dir: Path, db_path: Path, report_path: Path | None = None,
        rates: Rates | None = None) -> RunResult:
    raw = read_all(input_dir)
    shipments, ship_issues = validate_shipments(raw["shipments"])
    lines, line_issues = validate_lines(raw["lines"], shipments, raw["fx"], raw["tariffs"])
    costed = landed_cost(lines, shipments, raw["fx"], raw["tariffs"], rates)
    issues = pd.concat([ship_issues, line_issues], ignore_index=True)
    load(db_path, shipments, costed, issues)
    if report_path is not None:
        write_report(db_path, report_path)
    return RunResult(costed=costed, shipments=shipments, issues=issues)
