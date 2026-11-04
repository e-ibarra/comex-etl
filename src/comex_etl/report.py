"""Excel report built from the SQL views, formatted for people who open it in Excel."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .load import query

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")

SHEETS = {
    "Landed cost by SKU": "SELECT * FROM v_landed_cost_by_sku ORDER BY avg_landed_unit_usd DESC",
    "Suppliers": "SELECT * FROM v_spend_by_supplier ORDER BY rank_by_spend",
    "Monthly": "SELECT * FROM v_monthly_imports ORDER BY month",
    "Delays": "SELECT * FROM v_shipment_delays ORDER BY delay_days DESC",
    "Delay by port": "SELECT * FROM v_delay_by_port ORDER BY avg_delay_days DESC",
    "Duty by chapter": "SELECT * FROM v_duty_by_chapter ORDER BY duty_usd DESC",
    "Data quality": "SELECT * FROM data_quality_issues ORDER BY severity, rule, key",
}


def summary(db_path: Path) -> pd.DataFrame:
    totals = query(db_path, """
        SELECT COUNT(DISTINCT shipment_id) AS shipments, COUNT(*) AS lines,
               SUM(value_usd) AS purchases, SUM(landed_cost_usd) AS landed,
               SUM(cash_at_customs_usd) AS cash
        FROM costed_lines""").iloc[0]
    rejects = query(db_path, "SELECT COUNT(*) AS n FROM data_quality_issues "
                             "WHERE severity = 'reject'").iloc[0]["n"]
    warns = query(db_path, "SELECT COUNT(*) AS n FROM data_quality_issues "
                           "WHERE severity = 'warn'").iloc[0]["n"]
    late = query(db_path, "SELECT COUNT(*) AS n FROM v_shipment_delays "
                          "WHERE status IN ('late', 'very late')").iloc[0]["n"]
    return pd.DataFrame({
        "metric": ["Shipments costed", "Invoice lines costed", "Purchases (USD)",
                   "Landed cost (USD)", "Import multiplier", "Cash at customs (USD)",
                   "Late shipments", "Rows rejected", "Warnings"],
        "value": [int(totals.shipments), int(totals.lines), round(totals.purchases, 2),
                  round(totals.landed, 2), round(totals.landed / totals.purchases, 3),
                  round(totals.cash, 2), int(late), int(rejects), int(warns)],
    }, dtype=object)


def _format(ws) -> None:
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row), start=1):
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(idx)].width = min(max(width + 2, 10), 60)
        header = str(col[0].value or "")
        fmt = None
        if header.endswith("_usd") or header == "value":
            fmt = "#,##0.00"
        elif header in {"units", "qty", "shipments", "arrived"}:
            fmt = "#,##0"
        elif header.endswith("_pct"):
            fmt = "0.0"
        if fmt:
            for c in col[1:]:
                c.number_format = fmt
        col[0].value = _label(header)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _label(header: str) -> str:
    """``avg_landed_unit_usd`` → ``Avg landed unit (USD)`` for the people reading the sheet."""
    words = header.split("_")
    unit = None
    if words[-1] in {"usd", "pct"}:
        unit = {"usd": "USD", "pct": "%"}[words.pop()]
    acronyms = {"ncm": "NCM", "hs": "HS", "sku": "SKU", "etd": "ETD", "eta": "ETA",
                "fx": "FX"}
    text = " ".join(acronyms.get(w, w) for w in words)
    text = text[:1].upper() + text[1:]
    return f"{text} ({unit})" if unit else text


def write_report(db_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        summary(db_path).to_excel(xw, sheet_name="Summary", index=False)
        for name, sql in SHEETS.items():
            query(db_path, sql).to_excel(xw, sheet_name=name, index=False)
        for ws in xw.book.worksheets:
            _format(ws)
