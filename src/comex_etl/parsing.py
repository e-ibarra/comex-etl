"""Parsers for the values that real import files get wrong.

Every function here is pure: it takes one raw value and returns a clean value
or ``None``/``NaN``. They are applied column-wise in ``extract.py`` and tested
one by one in ``tests/test_parsing.py``.
"""

from __future__ import annotations

import math
import re
import unicodedata

# Legal-form suffixes that make the same supplier look like several.
_LEGAL_SUFFIXES = re.compile(
    r"\b(CO\s*LTD|COMPANY\s*LIMITED|CO|LTD|LIMITED|LLC|INC|CORP|CORPORATION|"
    r"S\s*A|S\s*R\s*L|SAS|GMBH|PTE|PVT|LTDA)\b"
)
_NUMBER_CLEAN = re.compile(r"[^\d,.\-]")


def parse_number(raw: object, decimal: str = ".") -> float:
    """Parse a money or quantity string written in either number locale.

    ``decimal`` is the separator the *source file* uses (``","`` for files
    exported with Spanish locale, ``"."`` otherwise). It only decides the
    ambiguous case of a single separator, such as ``"1,250"``. When both
    separators appear, the last one is the decimal separator, whatever the hint.

    >>> parse_number("USD 1.234,56", decimal=",")
    1234.56
    >>> parse_number("1,234.56")
    1234.56
    """
    if raw is None:
        return math.nan
    if isinstance(raw, (int, float)):
        return float(raw)
    s = _NUMBER_CLEAN.sub("", str(raw).strip())
    if s in {"", "-", ".", ","}:
        return math.nan
    negative = s.startswith("-")
    s = s.replace("-", "")
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        other = "," if sep == "." else "."
        groups = s.split(sep)
        if len(groups) > 2:
            # "1.234.567": a repeated separator can only be thousands.
            if not all(len(g) == 3 for g in groups[1:]):
                return math.nan
            dec = other
        elif sep == decimal:
            dec = sep  # "1234,5" in a comma-decimal file
        elif len(groups[1]) == 3:
            dec = other  # "1.250" in a comma-decimal file is one thousand two hundred fifty
        else:
            dec = sep  # "12.5" in a comma-decimal file can only be a decimal
    else:
        dec = "."
    thousands = "." if dec == "," else ","
    s = s.replace(thousands, "").replace(dec, ".")
    try:
        value = float(s)
    except ValueError:
        return math.nan
    return -value if negative else value


def normalize_ncm(raw: object) -> str | None:
    """Return an 8-digit NCM/HS code or ``None`` if it can't be one.

    Accepts ``"8471.30.12"``, ``"84713012"``, ``"8471 30 12"`` and the
    12-character form with a SIM suffix (``"8471.30.12.000A"``), which is
    truncated to its 8-digit NCM.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 8:
        return None
    return digits[:8]


def ncm_chapter(ncm: str | None) -> str | None:
    """Two-digit HS chapter (``"84"`` for machinery, ``"85"`` for electrical)."""
    return ncm[:2] if ncm else None


def normalize_supplier(raw: object) -> str | None:
    """Collapse spelling variants of a supplier name into one key.

    ``"Shenzhen Brightway Electronics Co., Ltd."`` and
    ``"SHENZHEN BRIGHTWAY ELECTRONICS CO LTD"`` both become
    ``"SHENZHEN BRIGHTWAY ELECTRONICS"``.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    s = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    s = re.sub(r"\s+", " ", s).strip()
    previous = None
    while previous != s:  # "... CO LTD" needs two passes after "LTD" goes
        previous = s
        s = _LEGAL_SUFFIXES.sub("", s).strip()
        s = re.sub(r"\s+", " ", s)
    return s or None


def normalize_currency(raw: object) -> str | None:
    """Map the currency spellings seen in supplier invoices to ISO codes."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    s = str(raw).strip().upper().replace(".", "")
    aliases = {
        "US$": "USD", "U$S": "USD", "U$D": "USD", "DOLAR": "USD", "DOLLAR": "USD",
        "RMB": "CNY", "YUAN": "CNY", "CNH": "CNY",
        "EURO": "EUR", "€": "EUR",
    }
    s = aliases.get(s, s)
    return s if re.fullmatch(r"[A-Z]{3}", s) else None
