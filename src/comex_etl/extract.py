"""Read the raw exports into typed DataFrames, one parser per column.

Nothing is dropped here: unparseable values become ``NaN``/``None`` and the
validation step decides what to reject, so every rejected row can be explained.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .parsing import normalize_currency, normalize_ncm, normalize_supplier, parse_number

SHIPMENT_COLUMNS = {
    "Embarque": "shipment_id",
    "Proveedor": "supplier_raw",
    "Incoterm": "incoterm",
    "Puerto origen": "origin_port",
    "ETD": "etd",
    "ETA": "eta",
    "Arribo real": "arrival",
    "Flete USD": "freight_usd",
    "Seguro USD": "insurance_usd",
    "Gastos locales ARS": "local_costs_ars",
}


def read_shipments(path: Path) -> pd.DataFrame:
    """Forwarder report: ``;``-separated, decimal comma, day-first dates."""
    raw = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    df = raw.rename(columns=SHIPMENT_COLUMNS)[list(SHIPMENT_COLUMNS.values())]
    df["shipment_id"] = df["shipment_id"].str.strip().str.upper()
    df["supplier"] = df["supplier_raw"].map(normalize_supplier)
    df["incoterm"] = df["incoterm"].str.strip().str.upper()
    for col in ("etd", "eta", "arrival"):
        df[col] = pd.to_datetime(df[col].replace("", None), format="%d/%m/%Y", errors="coerce")
    for col in ("freight_usd", "insurance_usd", "local_costs_ars"):
        df[col] = df[col].map(lambda v: parse_number(v, decimal=","))
    return df


def read_invoice_lines(path: Path) -> pd.DataFrame:
    """Supplier invoice lines: English locale, messy supplier/currency/NCM spellings."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["shipment_id"] = df["shipment_id"].str.strip().str.upper()
    df["line"] = pd.to_numeric(df["line"], errors="coerce").astype("Int64")
    df["supplier_raw"] = df["supplier"]
    df["supplier"] = df["supplier_raw"].map(normalize_supplier)
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], format="%Y-%m-%d", errors="coerce")
    df["ncm_raw"] = df["ncm"]
    df["ncm"] = df["ncm_raw"].map(normalize_ncm)
    df["qty"] = df["qty"].map(parse_number)
    df["unit_price"] = df["unit_price"].map(parse_number)
    df["currency_raw"] = df["currency"]
    df["currency"] = df["currency_raw"].map(normalize_currency)
    return df


def read_fx(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["currency"] = df["currency"].str.upper()
    return df.sort_values("date").reset_index(drop=True)


def read_tariffs(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ncm": str})
    df["ncm"] = df["ncm"].map(normalize_ncm)
    return df


def read_all(input_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "shipments": read_shipments(input_dir / "shipments_forwarder.csv"),
        "lines": read_invoice_lines(input_dir / "invoice_lines.csv"),
        "fx": read_fx(input_dir / "fx_rates.csv"),
        "tariffs": read_tariffs(input_dir / "tariffs.csv"),
    }
