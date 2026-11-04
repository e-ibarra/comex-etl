import math

import pytest

from comex_etl.parsing import (
    ncm_chapter,
    normalize_currency,
    normalize_ncm,
    normalize_supplier,
    parse_number,
)


@pytest.mark.parametrize(
    ("raw", "decimal", "expected"),
    [
        ("1.234,56", ",", 1234.56),       # Spanish-locale Excel export
        ("1,234.56", ".", 1234.56),       # English locale
        ("1,234.56", ",", 1234.56),       # both separators: last one wins, hint ignored
        ("USD 3.400,00", ",", 3400.0),    # currency prefix
        ("$ 12.5", ",", 12.5),            # decimal point in a comma file: only one reading
        ("1.250", ",", 1250.0),           # three digits after a dot in a comma file: thousands
        ("1,250", ".", 1250.0),           # the same, the other way round
        ("1250,5", ",", 1250.5),
        ("1.234.567", ",", 1234567.0),    # repeated separator is always thousands
        ("-45,10", ",", -45.10),
        (980, ".", 980.0),
        (2.5, ",", 2.5),
    ],
)
def test_parse_number(raw, decimal, expected):
    assert parse_number(raw, decimal=decimal) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "  ", "-", "N/A", None, "1.23.4"])
def test_parse_number_returns_nan_for_garbage(raw):
    assert math.isnan(parse_number(raw))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8471.30.12", "84713012"),
        ("84713012", "84713012"),
        ("8471 30 12", "84713012"),
        ("8504.40.90.000A", "85044090"),  # SIM suffix dropped
        ("8504.40", None),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_normalize_ncm(raw, expected):
    assert normalize_ncm(raw) == expected


def test_ncm_chapter():
    assert ncm_chapter("85044090") == "85"
    assert ncm_chapter(None) is None


@pytest.mark.parametrize(
    "raw",
    [
        "Shenzhen Brightway Electronics Co., Ltd.",
        "SHENZHEN BRIGHTWAY ELECTRONICS CO LTD",
        "Shenzhen Brightway Electronics",
        "  shenzhen   brightway electronics co.,ltd ",
    ],
)
def test_supplier_variants_collapse_to_one_key(raw):
    assert normalize_supplier(raw) == "SHENZHEN BRIGHTWAY ELECTRONICS"


def test_supplier_strips_accents_and_other_legal_forms():
    assert normalize_supplier("Milano Precision S.r.l.") == "MILANO PRECISION"
    assert normalize_supplier("Logística Fueguina S.A.") == "LOGISTICA FUEGUINA"
    assert normalize_supplier("") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("usd", "USD"), ("US$", "USD"), ("U$S", "USD"), ("RMB", "CNY"), ("Euro", "EUR"),
     ("EUR", "EUR"), ("XYZ", "XYZ"), ("", None), ("12", None)],
)
def test_normalize_currency(raw, expected):
    assert normalize_currency(raw) == expected
