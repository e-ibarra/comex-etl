import pandas as pd

from comex_etl.validate import validate_lines, validate_shipments

FX = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "currency": ["CNY"],
                   "usd_per_unit": [0.14]})
TARIFFS = pd.DataFrame({"ncm": ["85044090"], "duty_rate": [0.14]})
SHIPMENTS = pd.DataFrame({"shipment_id": ["S1"], "supplier": ["ACME"]})


def line(**over):
    base = {"invoice_no": "I1", "line": 1, "shipment_id": "S1", "supplier": "ACME",
            "supplier_raw": "Acme Co Ltd", "invoice_date": pd.Timestamp("2026-03-01"),
            "ncm_raw": "8504.40.90", "ncm": "85044090", "qty": 10.0, "unit_price": 2.0,
            "currency_raw": "USD", "currency": "USD"}
    base.update(over)
    return base


def rules(rows):
    _, issues = validate_lines(pd.DataFrame(rows), SHIPMENTS, FX, TARIFFS)
    return issues.set_index("key")["rule"].to_dict()


def test_clean_line_passes():
    clean, issues = validate_lines(pd.DataFrame([line()]), SHIPMENTS, FX, TARIFFS)
    assert len(clean) == 1 and issues.empty


def test_each_rule():
    found = rules([
        line(line=1),
        line(line=1),                                         # duplicate
        line(line=2, ncm_raw="", ncm=None),
        line(line=3, ncm_raw="8504.40", ncm=None),
        line(line=4, qty=0.0),
        line(line=5, unit_price=float("nan")),
        line(line=6, currency_raw="XYZ", currency="XYZ"),
        line(line=7, shipment_id="S9"),
        line(line=8, ncm_raw="9999.99.99", ncm="99999999"),
        line(line=9, currency="CNY", invoice_date=pd.Timestamp("2025-12-20")),
    ])
    assert found == {
        "I1/1": "duplicate_line", "I1/2": "missing_ncm", "I1/3": "invalid_ncm",
        "I1/4": "non_positive_qty", "I1/5": "missing_price", "I1/6": "unknown_currency",
        "I1/7": "unknown_shipment", "I1/8": "no_tariff", "I1/9": "no_fx_rate",
    }


def test_a_row_is_reported_under_its_first_failing_rule_only():
    found = rules([line(ncm_raw="", ncm=None, qty=0.0, currency="XYZ")])
    assert found == {"I1/1": "missing_ncm"}


def test_supplier_mismatch_is_a_warning_not_a_reject():
    clean, issues = validate_lines(pd.DataFrame([line(supplier="OTHER")]), SHIPMENTS, FX,
                                   TARIFFS)
    assert len(clean) == 1
    assert issues.iloc[0][["rule", "severity"]].tolist() == ["supplier_mismatch", "warn"]


def test_shipment_rules():
    ship = pd.DataFrame({
        "shipment_id": ["S1", "S2", "S3", "S4"],
        "incoterm": ["FOB", "DDP", "CIF", "FOB"],
        "etd": pd.to_datetime(["2026-01-10", "2026-01-10", "2026-01-10", None]),
        "arrival": pd.to_datetime([None, "2026-02-10", "2026-02-10", "2026-02-10"]),
        "freight_usd": [100.0, 100.0, 250.0, 100.0],
    })
    kept, issues = validate_shipments(ship)
    assert kept["shipment_id"].tolist() == ["S1", "S3"]
    assert issues.set_index("key")["rule"].to_dict() == {
        "S2": "unsupported_incoterm", "S4": "missing_etd", "S1": "in_transit",
        "S3": "freight_on_cif",
    }
