"""End to end on the fictional sample: every planted defect is caught, nothing
else is lost, and the SQL views agree with the costed lines."""

import sqlite3

import pandas as pd
import pytest
from openpyxl import load_workbook

from comex_etl.cli import main
from comex_etl.extract import read_invoice_lines
from comex_etl.load import query
from comex_etl.pipeline import run
from comex_etl.report import SHEETS
from comex_etl.sample import EXPECTED_REJECTS, SUPPLIERS, generate


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("run")
    generate(base / "in")
    res = run(base / "in", base / "comex.db", base / "report.xlsx")
    return res, base


def test_each_planted_defect_is_rejected_once(result):
    res, _ = result
    rejects = res.issues.query("severity == 'reject'")["rule"].value_counts().to_dict()
    assert rejects == EXPECTED_REJECTS


def test_every_raw_line_is_either_costed_or_rejected(result):
    res, base = result
    raw = read_invoice_lines(base / "in" / "invoice_lines.csv")
    rejected = res.issues.query("source == 'invoice_lines' and severity == 'reject'")
    assert len(res.costed) + len(rejected) == len(raw)


def test_supplier_spellings_collapse_to_the_real_suppliers(result):
    res, _ = result
    assert res.costed["supplier"].nunique() <= len(SUPPLIERS)
    assert not res.issues["rule"].eq("supplier_mismatch").any()


def test_views_reconcile_with_costed_lines(result):
    res, base = result
    db = base / "comex.db"
    total = res.costed["landed_cost_usd"].sum()
    by_supplier = query(db, "SELECT SUM(landed_cost_usd) AS t FROM v_spend_by_supplier")
    by_month = query(db, "SELECT MAX(cumulative_landed_usd) AS t FROM v_monthly_imports")
    assert by_supplier.t[0] == pytest.approx(total, abs=0.05)
    assert by_month.t[0] == pytest.approx(total, abs=0.05)
    share = query(db, "SELECT SUM(share_pct) AS s FROM v_spend_by_supplier").s[0]
    assert share == pytest.approx(100, abs=0.3)


def test_in_transit_shipment_is_flagged_and_kept_out_of_delay_averages(result):
    _, base = result
    db = base / "comex.db"
    status = query(db, "SELECT status FROM v_shipment_delays WHERE shipment_id = 'SHP-2026-024'")
    assert status.status[0] == "in transit"
    arrived = query(db, "SELECT SUM(arrived) AS n FROM v_delay_by_port").n[0]
    total = query(db, "SELECT COUNT(*) AS n FROM shipments").n[0]
    assert arrived == total - 1


def test_landed_cost_is_never_below_purchase_price(result):
    res, _ = result
    assert (res.costed["landed_cost_usd"] >= res.costed["value_usd"]).all()
    assert res.costed["landed_unit_usd"].notna().all()


def test_report_has_every_sheet(result):
    _, base = result
    wb = load_workbook(base / "report.xlsx")
    assert wb.sheetnames == ["Summary", *SHEETS]
    assert wb["Landed cost by SKU"].freeze_panes == "A2"


def test_rerun_replaces_tables_instead_of_appending(result):
    res, base = result
    run(base / "in", base / "comex.db")
    with sqlite3.connect(base / "comex.db") as con:
        n = pd.read_sql_query("SELECT COUNT(*) AS n FROM costed_lines", con).n[0]
    assert n == len(res.costed)


def test_cli_runs(tmp_path, capsys):
    assert main(["sample", "--out", str(tmp_path / "in")]) == 0
    assert main(["run", "--input", str(tmp_path / "in"), "--db", str(tmp_path / "x.db"),
                 "--report", str(tmp_path / "x.xlsx")]) == 0
    out = capsys.readouterr().out
    assert "Landed cost (USD)" in out and "missing_ncm" in out
