"""Landed cost against numbers worked out by hand.

FOB shipment, two lines, both invoiced in USD:

    A: 100 u × 10.00 = 1,000      NCM 85044090, duty 20 %
    B:  50 u × 20.00 = 1,000      NCM 39269090, duty 10 %
    freight 300, insurance 20, local costs ARS 1,000,000 at 0.001 = USD 1,000

Each line carries half of everything (equal values), so for A:

    customs value = 1,000 + 150 + 10       = 1,160.00
    duty          = 1,160 × 20 %           =   232.00
    statistics    = 1,160 × 3 %            =    34.80
    tax base      = 1,160 + 232 + 34.80    = 1,426.80
    landed        = 1,426.80 + 500         = 1,926.80  → 19.268 per unit
    recoverable   = 1,426.80 × 49.5 %      =   706.266
and for B: 1,160 + 116 + 34.80 + 500 = 1,810.80 → 36.216 per unit.
"""

import pandas as pd
import pytest

from comex_etl.costing import Rates, attach_fx, landed_cost

FX = pd.DataFrame({
    "date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-01-01"]),
    "currency": ["CNY", "CNY", "ARS"],
    "usd_per_unit": [0.14, 0.15, 0.001],
}).sort_values("date")
TARIFFS = pd.DataFrame({"ncm": ["85044090", "39269090"], "duty_rate": [0.20, 0.10]})


def shipment(incoterm="FOB", freight=300.0, insurance=20.0, local_ars=1_000_000.0):
    return pd.DataFrame([{
        "shipment_id": "S1", "supplier": "ACME", "incoterm": incoterm, "origin_port": "Ningbo",
        "etd": pd.Timestamp("2026-02-10"), "eta": pd.Timestamp("2026-03-20"),
        "arrival": pd.Timestamp("2026-03-22"), "freight_usd": freight,
        "insurance_usd": insurance, "local_costs_ars": local_ars,
    }])


def lines(currency="USD", prices=(10.0, 20.0)):
    return pd.DataFrame({
        "invoice_no": ["I1", "I1"], "line": [1, 2], "shipment_id": ["S1", "S1"],
        "supplier": ["ACME", "ACME"], "invoice_date": pd.to_datetime(["2026-02-05"] * 2),
        "sku": ["A", "B"], "description": ["a", "b"], "ncm": ["85044090", "39269090"],
        "qty": [100.0, 50.0], "unit_price": list(prices), "currency": [currency, currency],
    })


def test_fob_shipment_matches_hand_worked_example():
    out = landed_cost(lines(), shipment(), FX, TARIFFS).set_index("sku")
    a, b = out.loc["A"], out.loc["B"]
    assert a.customs_value_usd == pytest.approx(1160.0)
    assert a.duty_usd == pytest.approx(232.0)
    assert a.statistics_usd == pytest.approx(34.8)
    assert a.local_costs_alloc_usd == pytest.approx(500.0)
    assert a.landed_cost_usd == pytest.approx(1926.8)
    assert a.landed_unit_usd == pytest.approx(19.268)
    assert a.recoverable_taxes_usd == pytest.approx(706.266)
    assert b.landed_unit_usd == pytest.approx(36.216)


def test_allocations_add_back_to_the_shipment_totals():
    out = landed_cost(lines(prices=(7.0, 31.0)), shipment(), FX, TARIFFS)
    assert out.freight_alloc_usd.sum() == pytest.approx(300.0)
    assert out.insurance_alloc_usd.sum() == pytest.approx(20.0)
    assert out.local_costs_alloc_usd.sum() == pytest.approx(1000.0)


def test_cif_does_not_add_freight_or_insurance_again():
    out = landed_cost(lines(), shipment("CIF", freight=300.0), FX, TARIFFS)
    assert (out.customs_value_usd == out.value_usd).all()


def test_cfr_adds_insurance_only():
    out = landed_cost(lines(), shipment("CFR"), FX, TARIFFS)
    assert out.freight_alloc_usd.sum() == 0
    assert out.customs_value_usd.sum() == pytest.approx(2020.0)


def test_foreign_currency_uses_last_rate_on_or_before_invoice_date():
    # Invoice dated 2026-02-05 → February rate 0.15, not January's 0.14.
    out = landed_cost(lines("CNY", prices=(100.0, 200.0)), shipment(), FX, TARIFFS)
    assert out.fx_usd.tolist() == [0.15, 0.15]
    assert out.value_usd.sum() == pytest.approx(100 * 100 * 0.15 + 50 * 200 * 0.15)


def test_attach_fx_keeps_row_order_with_mixed_currencies():
    df = pd.DataFrame({"d": pd.to_datetime(["2026-02-03", "2026-01-15", "2026-02-20"]),
                       "c": ["CNY", "USD", "CNY"]})
    out = attach_fx(df, FX, "d", "c", "rate")
    assert out.c.tolist() == ["CNY", "USD", "CNY"]
    assert out.rate.tolist() == [0.15, 1.0, 0.15]


def test_rates_are_editable():
    no_tax = Rates(statistics=0, vat=0, vat_additional=0, income_tax_prepayment=0,
                   gross_income_prepayment=0)
    out = landed_cost(lines(), shipment(local_ars=0), FX, TARIFFS, no_tax)
    assert out.statistics_usd.sum() == 0
    assert out.recoverable_taxes_usd.sum() == 0
    assert out.landed_cost_usd.sum() == pytest.approx(2320 + 232 + 116)
