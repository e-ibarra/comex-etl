"""Load clean tables into SQLite and create the analysis views."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

import pandas as pd

COSTED_COLUMNS = [
    "shipment_id", "invoice_no", "line", "supplier", "invoice_date", "sku", "description", "ncm",
    "qty", "unit_price", "currency", "fx_usd", "value_usd", "incoterm", "origin_port", "etd",
    "eta", "arrival", "freight_alloc_usd", "insurance_alloc_usd", "customs_value_usd",
    "duty_rate", "duty_usd", "statistics_usd", "recoverable_taxes_usd", "local_costs_alloc_usd",
    "landed_cost_usd", "price_unit_usd", "landed_unit_usd", "cash_at_customs_usd",
    "import_multiplier",
]
SHIPMENT_COLUMNS = [
    "shipment_id", "supplier", "incoterm", "origin_port", "etd", "eta", "arrival",
    "freight_usd", "insurance_usd", "local_costs_ars",
]


def views_sql() -> str:
    return resources.files("comex_etl").joinpath("sql/views.sql").read_text(encoding="utf-8")


def load(db_path: Path, shipments: pd.DataFrame, costed: pd.DataFrame,
         issues: pd.DataFrame) -> None:
    """Replace the tables in ``db_path`` (a full reload keeps runs reproducible)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        shipments[SHIPMENT_COLUMNS].to_sql("shipments", con, if_exists="replace", index=False)
        costed[COSTED_COLUMNS].to_sql("costed_lines", con, if_exists="replace", index=False)
        issues.to_sql("data_quality_issues", con, if_exists="replace", index=False)
        con.executescript(views_sql())


def query(db_path: Path, sql: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(sql, con)
