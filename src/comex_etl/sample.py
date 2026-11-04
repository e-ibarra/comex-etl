"""Generate the fictional sample dataset in ``data/sample``.

The data imitates three real exports an import analyst juggles: the freight
forwarder's shipment report (Spanish locale: ``;`` separator, decimal comma,
day-first dates), supplier invoice lines (English locale, inconsistent supplier
and currency spellings) and a monthly FX table. Companies, SKUs and amounts are
invented. A handful of defects are planted on purpose so the validation step has
something to catch; ``EXPECTED_REJECTS`` lists them and a test checks that each
one is caught.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SUPPLIERS = [
    # (canonical-ish name, spelling variants seen on invoices, currency, origin port)
    ("Shenzhen Brightway Electronics Co., Ltd.",
     ["Shenzhen Brightway Electronics Co., Ltd.", "SHENZHEN BRIGHTWAY ELECTRONICS CO LTD",
      "Shenzhen Brightway Electronics"], "USD", "Shenzhen"),
    ("Ningbo Harbor Plastics Co Ltd",
     ["Ningbo Harbor Plastics Co Ltd", "NINGBO HARBOR PLASTICS CO., LIMITED"], "CNY", "Ningbo"),
    ("Dongguan Everlight Components",
     ["Dongguan Everlight Components", "Dongguan Everlight Components Co.,Ltd"], "USD", "Shenzhen"),
    ("Milano Precision S.r.l.", ["Milano Precision S.r.l.", "MILANO PRECISION SRL"], "EUR",
     "Genova"),
    ("Austin Circuit Supply Inc.", ["Austin Circuit Supply Inc.", "Austin Circuit Supply"], "USD",
     "Houston"),
]

# sku, description, NCM as written on invoices, unit price in USD, supplier index
PRODUCTS = [
    ("LED-PNL-60", "LED panel 60x60 40W", "9405.42.00", 11.80, 0),
    ("PSU-12V-5A", "Power supply 12V 5A", "8504.40.90", 4.15, 0),
    ("PSU-24V-10A", "Power supply 24V 10A", "8504.40.90", 9.60, 2),
    ("HSG-ABS-S", "ABS housing small", "3926.90.90", 0.62, 1),
    ("HSG-ABS-L", "ABS housing large", "3926.90.90", 1.35, 1),
    ("CBL-USB-C1", "USB-C cable 1m", "8544.42.00", 0.95, 2),
    ("PCB-CTRL-A", "Controller board rev A", "8473.30.99", 23.40, 4),
    ("VLV-SOL-12", "Solenoid valve 12V", "8481.80.99", 38.00, 3),
]

# Planning rates for the sample, not an official tariff schedule.
TARIFFS = [
    ("94054200", 0.20), ("85044090", 0.14), ("39269090", 0.18),
    ("85444200", 0.16), ("84733099", 0.0), ("84818099", 0.14),
]

FX_MONTHLY = {  # USD per unit of currency, first of each month (invented, plausible)
    "CNY": [0.1379, 0.1382, 0.1385, 0.1381, 0.1390, 0.1394, 0.1398, 0.1401, 0.1397, 0.1403],
    "EUR": [1.034, 1.041, 1.079, 1.122, 1.131, 1.155, 1.168, 1.162, 1.171, 1.158],
    "ARS": [0.000951, 0.000939, 0.000921, 0.000874, 0.000862, 0.000851, 0.000812, 0.000779,
            0.000741, 0.000722, 0.000718, 0.000715],
}

EXPECTED_REJECTS = {
    "missing_ncm": 2,
    "invalid_ncm": 1,
    "non_positive_qty": 1,
    "unknown_currency": 1,
    "unknown_shipment": 1,
    "duplicate_line": 1,
}


def _fmt_es(x: float) -> str:
    """Format a number the way a Spanish-locale Excel export does: 1.234,56."""
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def generate(out_dir: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    shipments, lines = [], []
    for n in range(1, 25):
        sup_idx = rng.randrange(len(SUPPLIERS))
        name, variants, currency, port = SUPPLIERS[sup_idx]
        etd = date(2026, 1, 15) + timedelta(days=rng.randrange(0, 255))
        transit = {"Genova": 28, "Houston": 24}.get(port, 42)
        eta = etd + timedelta(days=transit)
        delay = rng.choice([-2, -1, 0, 0, 0, 0, 3, 6, 11, 18])
        arrival = eta + timedelta(days=delay)
        incoterm = rng.choice(["FOB", "FOB", "FOB", "CIF"])
        sid = f"SHP-2026-{n:03d}"
        candidates = [p for p in PRODUCTS if p[4] == sup_idx] or [PRODUCTS[0]]
        picked = rng.sample(candidates, k=min(len(candidates), rng.randint(1, 3)))
        invoice_total_usd = 0.0
        for i, (sku, desc, ncm, usd_price, _) in enumerate(picked, start=1):
            # Buyers order cheap parts by the tens of thousands: aim each line at
            # USD 6k-40k so freight is spread the way it is on a real container.
            qty = int(max(100, round(rng.uniform(6_000, 40_000) / usd_price, -2)))
            if currency == "USD":
                price = usd_price
            else:
                rate = FX_MONTHLY[currency][etd.month - 1]
                price = round(usd_price / rate, 2)
            if incoterm == "CIF":
                price = round(price * 1.07, 2)  # supplier bakes freight in
            invoice_total_usd += qty * usd_price
            lines.append({
                "invoice_no": f"INV-{n:03d}",
                "shipment_id": sid,
                "line": i,
                "supplier": rng.choice(variants),
                "invoice_date": (etd - timedelta(days=rng.randint(3, 10))).isoformat(),
                "sku": sku,
                "description": desc,
                "ncm": rng.choice([ncm, ncm.replace(".", ""), ncm + ".000A"]),
                "qty": qty,
                "unit_price": rng.choice([f"{price:.2f}", f"{price:,.2f}"]),
                "currency": {"USD": rng.choice(["USD", "US$", "usd"]),
                             "CNY": rng.choice(["CNY", "RMB"]),
                             "EUR": rng.choice(["EUR", "Euro"])}[currency],
            })
        freight = 0.0 if incoterm == "CIF" else round(900 + rng.random() * 2600, 2)
        insurance = 0.0 if incoterm == "CIF" else round(
            (invoice_total_usd + freight) * 1.1 * 0.003, 2)
        shipments.append({
            "Embarque": sid,
            "Proveedor": name,
            "Incoterm": incoterm,
            "Puerto origen": port,
            "ETD": etd.strftime("%d/%m/%Y"),
            "ETA": eta.strftime("%d/%m/%Y"),
            "Arribo real": arrival.strftime("%d/%m/%Y") if n != 24 else "",  # still at sea
            "Flete USD": _fmt_es(freight),
            "Seguro USD": _fmt_es(insurance),
            "Gastos locales ARS": _fmt_es(rng.choice([380_000, 520_000, 745_000])),
        })

    # Planted defects (see EXPECTED_REJECTS).
    lines[3]["ncm"] = ""
    lines[17]["ncm"] = "N/A"
    lines[8]["ncm"] = "8504.40"
    lines[11]["qty"] = 0
    lines[20]["currency"] = "XYZ"
    orphan = dict(lines[5], shipment_id="SHP-2026-099", invoice_no="INV-099")
    lines.append(orphan)
    lines.append(dict(lines[0]))  # the same line exported twice

    with (out_dir / "shipments_forwarder.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(shipments[0]), delimiter=";")
        w.writeheader()
        w.writerows(shipments)
    with (out_dir / "invoice_lines.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lines[0]))
        w.writeheader()
        w.writerows(lines)
    with (out_dir / "fx_rates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "currency", "usd_per_unit"])
        for cur, rates in FX_MONTHLY.items():
            for m, r in enumerate(rates, start=1):
                w.writerow([date(2026, m, 1).isoformat(), cur, r])
    with (out_dir / "tariffs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ncm", "duty_rate"])
        w.writerows(TARIFFS)
