"""Data-quality rules.

Each rule either **rejects** a row (it can't be costed honestly) or **warns**
(it can be costed, but someone should look). Every finding goes to one issues
table that ends up in the database and in the report, so nothing disappears
silently.
"""

from __future__ import annotations

import pandas as pd

SUPPORTED_INCOTERMS = {"FOB", "CFR", "CIF"}
ISSUE_COLUMNS = ["source", "key", "rule", "severity", "detail"]


def _issues(rows: pd.DataFrame, source: str, rule: str, severity: str, detail) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=ISSUE_COLUMNS)
    if source == "invoice_lines":
        key = rows["invoice_no"] + "/" + rows["line"].astype("string")
    else:
        key = rows["shipment_id"]
    if callable(detail):
        details = [detail(r) for r in rows.itertuples(index=False)]
    else:
        details = [detail] * len(rows)
    return pd.DataFrame({
        "source": source, "key": key.to_numpy(), "rule": rule, "severity": severity,
        "detail": details,
    })


def validate_shipments(ship: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    found = []
    bad_term = ~ship["incoterm"].isin(SUPPORTED_INCOTERMS)
    found.append(_issues(ship[bad_term], "shipments", "unsupported_incoterm", "reject",
                         lambda r: f"Incoterm '{r.incoterm}' (supported: FOB, CFR, CIF)"))
    no_etd = ship["etd"].isna()
    found.append(_issues(ship[no_etd], "shipments", "missing_etd", "reject", "ETD is empty"))
    rejected = bad_term | no_etd

    in_transit = ship["arrival"].isna() & ~rejected
    found.append(_issues(ship[in_transit], "shipments", "in_transit", "warn",
                         "No arrival date yet; excluded from delay figures"))
    freight_in_c = ship["incoterm"].eq("CIF") & (ship["freight_usd"].fillna(0) > 0)
    found.append(_issues(ship[freight_in_c], "shipments", "freight_on_cif", "warn",
                         "Freight reported on a CIF shipment; ignored (already in the price)"))
    return ship[~rejected].copy(), pd.concat(found, ignore_index=True)


def validate_lines(
    lines: pd.DataFrame, shipments: pd.DataFrame, fx: pd.DataFrame, tariffs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    found = []
    reject = pd.Series(False, index=lines.index)

    def rule(mask: pd.Series, name: str, detail) -> None:
        nonlocal reject
        mask = mask & ~reject  # report each row once, under its first failing rule
        found.append(_issues(lines[mask], "invoice_lines", name, "reject", detail))
        reject = reject | mask

    dup = lines.duplicated(subset=["invoice_no", "line"], keep="first")
    rule(dup, "duplicate_line", "Same invoice number and line already loaded")
    raw_ncm_digits = lines["ncm_raw"].str.replace(r"\D", "", regex=True)
    rule(raw_ncm_digits.eq(""), "missing_ncm", lambda r: f"NCM field: '{r.ncm_raw}'")
    rule(lines["ncm"].isna(), "invalid_ncm", lambda r: f"'{r.ncm_raw}' has fewer than 8 digits")
    rule(~(lines["qty"] > 0), "non_positive_qty", lambda r: f"Quantity: {r.qty}")
    rule(~(lines["unit_price"] > 0), "missing_price", "Unit price is empty or zero")
    rule(lines["currency"].isna() | ~lines["currency"].isin({"USD", *fx["currency"].unique()}),
         "unknown_currency", lambda r: f"Currency '{r.currency_raw}' has no FX table")
    rule(~lines["shipment_id"].isin(shipments["shipment_id"]), "unknown_shipment",
         lambda r: f"{r.shipment_id} is not in the forwarder report")
    rule(~lines["ncm"].isin(tariffs["ncm"]), "no_tariff",
         lambda r: f"NCM {r.ncm} has no duty rate in tariffs.csv")

    first_rate = fx.groupby("currency")["date"].min()
    needs_fx = lines["currency"].ne("USD") & lines["currency"].isin(first_rate.index)
    too_early = needs_fx & (
        lines["invoice_date"] < lines["currency"].map(first_rate).fillna(pd.Timestamp.max)
    )
    rule(too_early, "no_fx_rate", "No FX rate on or before the invoice date")

    clean = lines[~reject].copy()
    ship_supplier = clean["shipment_id"].map(shipments.set_index("shipment_id")["supplier"])
    mismatch = clean["supplier"].ne(ship_supplier)
    found.append(_issues(clean[mismatch], "invoice_lines", "supplier_mismatch", "warn",
                         lambda r: f"Invoice says '{r.supplier_raw}', forwarder says otherwise"))
    return clean, pd.concat(found, ignore_index=True)
