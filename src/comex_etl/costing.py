"""Landed cost per invoice line.

The chain, per shipment, then allocated to its lines by value::

    line value USD   = qty × unit price × FX (rate on or before the invoice date)
    customs value    = FOB: value + freight + insurance
                       CFR: value + insurance          (freight is in the price)
                       CIF: value                      (both are in the price)
    duty             = customs value × duty rate of the line's NCM
    statistics fee   = customs value × statistics rate
    local costs USD  = forwarder's local costs in ARS, converted at the ETA rate
    landed cost      = customs value + duty + statistics fee + local costs
    cash at customs  = duty + statistics fee + VAT, additional VAT and prepayments
                       on (customs value + duty + statistics fee)

VAT and the prepayments are cash you need on clearance day but a registered
business recovers them, so they are kept out of landed cost. This is the same
split the companion calculator (github.com/e-ibarra/landed-cost) makes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Rates:
    """Argentine general-regime defaults; editable because they change."""

    statistics: float = 0.03
    vat: float = 0.21
    vat_additional: float = 0.20
    income_tax_prepayment: float = 0.06
    gross_income_prepayment: float = 0.025

    @property
    def recoverable(self) -> float:
        return (self.vat + self.vat_additional + self.income_tax_prepayment
                + self.gross_income_prepayment)


def attach_fx(df: pd.DataFrame, fx: pd.DataFrame, date_col: str, cur_col: str,
              out_col: str) -> pd.DataFrame:
    """Add the USD rate valid on ``date_col`` (last rate on or before it)."""
    df = df.copy()
    df["_order"] = range(len(df))
    usd = df[cur_col].eq("USD")
    left = df[~usd].sort_values(date_col)
    if left.empty:
        merged = left.assign(**{out_col: pd.Series(dtype=float)})
    else:
        merged = pd.merge_asof(
            left, fx.rename(columns={"date": "_fx_date", "usd_per_unit": out_col,
                                     "currency": cur_col}).sort_values("_fx_date"),
            left_on=date_col, right_on="_fx_date", by=cur_col, direction="backward",
        ).drop(columns="_fx_date")
    out = pd.concat([df[usd].assign(**{out_col: 1.0}), merged], ignore_index=True)
    return out.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def _allocate(df: pd.DataFrame, total_col: str, weight_col: str) -> pd.Series:
    """Spread a per-shipment amount over its lines in proportion to ``weight_col``."""
    share = df[weight_col] / df.groupby("shipment_id")[weight_col].transform("sum")
    return df[total_col].fillna(0.0) * share


def landed_cost(lines: pd.DataFrame, shipments: pd.DataFrame, fx: pd.DataFrame,
                tariffs: pd.DataFrame, rates: Rates | None = None) -> pd.DataFrame:
    """Return one costed row per invoice line. Inputs must already be validated."""
    rates = rates or Rates()
    df = attach_fx(lines, fx, "invoice_date", "currency", "fx_usd")
    df["value_usd"] = df["qty"] * df["unit_price"] * df["fx_usd"]

    ship = shipments.copy()
    ship["currency_local"] = "ARS"
    ship = attach_fx(ship, fx, "eta", "currency_local", "ars_fx_usd")
    ship["local_costs_usd"] = ship["local_costs_ars"] * ship["ars_fx_usd"]
    keep = ["shipment_id", "incoterm", "origin_port", "etd", "eta", "arrival",
            "freight_usd", "insurance_usd", "local_costs_usd"]
    df = df.merge(ship[keep], on="shipment_id", how="left", validate="many_to_one")

    pays_freight = df["incoterm"].eq("FOB")
    pays_insurance = df["incoterm"].isin({"FOB", "CFR"})
    df["freight_alloc_usd"] = _allocate(df, "freight_usd", "value_usd").where(pays_freight, 0.0)
    df["insurance_alloc_usd"] = _allocate(df, "insurance_usd", "value_usd").where(
        pays_insurance, 0.0)
    df["local_costs_alloc_usd"] = _allocate(df, "local_costs_usd", "value_usd")

    df["customs_value_usd"] = df["value_usd"] + df["freight_alloc_usd"] + df["insurance_alloc_usd"]
    df["duty_rate"] = df["ncm"].map(tariffs.set_index("ncm")["duty_rate"])
    df["duty_usd"] = df["customs_value_usd"] * df["duty_rate"]
    df["statistics_usd"] = df["customs_value_usd"] * rates.statistics
    tax_base = df["customs_value_usd"] + df["duty_usd"] + df["statistics_usd"]
    df["recoverable_taxes_usd"] = tax_base * rates.recoverable
    df["landed_cost_usd"] = tax_base + df["local_costs_alloc_usd"]
    df["landed_unit_usd"] = df["landed_cost_usd"] / df["qty"]
    df["price_unit_usd"] = df["value_usd"] / df["qty"]
    df["cash_at_customs_usd"] = df["duty_usd"] + df["statistics_usd"] + df["recoverable_taxes_usd"]
    df["import_multiplier"] = df["landed_cost_usd"] / df["value_usd"]
    return df
