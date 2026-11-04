# comex-etl

[![test](https://github.com/e-ibarra/comex-etl/actions/workflows/test.yml/badge.svg)](https://github.com/e-ibarra/comex-etl/actions/workflows/test.yml)

**Turn the messy exports an import analyst lives in into one clean table of landed cost per SKU, a SQL database and an Excel report.**

Python · pandas · SQL (SQLite) · pytest · GitHub Actions

An import department usually works from three files that don't agree with each other: the freight forwarder's shipment report (exported with Spanish locale, so `1.468,46` and `21/01/2026`), the suppliers' invoice lines (English locale, a supplier spelled three ways, NCM codes with and without dots, `US$`, `RMB` and `Euro` as currencies) and an FX table. This pipeline reads all of them, rejects what can't be costed and says why, computes what each unit really cost once it reached the warehouse, and loads the result into SQL views that answer the questions management actually asks.

It is the batch, many-shipments companion of [landed-cost](https://github.com/e-ibarra/landed-cost), the browser calculator for a single quote, and uses the same cost logic.

## What it does

```
data/sample/*.csv ──► extract ──► validate ──► cost ──► SQLite ──► SQL views ──► Excel report
                     (parse per    (reject or   (FX, CIF,  (tables   (by SKU,       (formatted,
                      locale)       warn, with   duty,      replaced  supplier,      one sheet
                                    a reason)    taxes)     per run)  port, month)   per view)
```

- **Parses both number locales.** `1.234,56`, `1,234.56`, `USD 3.400,00` and `12.5` in a comma-decimal file all come out right. The file's locale is an explicit argument; it only settles the one ambiguous case (`1,250`), and that rule is tested.
- **Normalizes what breaks joins.** NCM codes become 8 digits (`8504.40.90.000A` → `85044090`), supplier names lose case, accents and legal suffixes (`Shenzhen Brightway Electronics Co., Ltd.` and `SHENZHEN BRIGHTWAY ELECTRONICS CO LTD` are one supplier), currency spellings map to ISO codes.
- **Never drops a row silently.** Each row either gets costed or lands in `data_quality_issues` with the rule it broke: duplicate line, missing or short NCM, zero quantity, missing price, unknown currency, no FX rate for that date, shipment not in the forwarder report, NCM with no duty rate. Shipments still at sea or with freight reported on a CIF term are kept but flagged. A test checks that costed rows + rejected rows = raw rows.
- **Costs each line** under FOB, CFR or CIF: FX at the last rate on or before the invoice date, freight, insurance and local costs allocated by value, duty by NCM, statistics fee, and the VAT/prepayment cash you need at customs kept apart from the cost you keep.
- **SQL views** for landed cost by SKU, spend by supplier (with rank and share, using window functions), shipment delays and delay by origin port, duty by HS chapter, and monthly imports with a running total.
- **Excel report** with one formatted sheet per view plus a summary and the data-quality log: header styling, frozen header row, filters, number formats, sensible column widths. [Download the sample report](docs/sample_report.xlsx).

## Sample output

From the fictional dataset in `data/sample` (24 shipments, 5 suppliers, 8 SKUs, 7 planted defects):

| SKU | Units | Avg price USD | Avg landed USD/unit | Multiplier |
|:--|--:|--:|--:|--:|
| LED-PNL-60 | 14,400 | 11.80 | 15.59 | 1.32 |
| VLV-SOL-12 | 1,800 | 38.05 | 50.15 | 1.32 |
| CBL-USB-C1 | 96,500 | 0.95 | 1.22 | 1.29 |
| PSU-24V-10A | 3,300 | 9.60 | 12.23 | 1.27 |
| PSU-12V-5A | 18,700 | 4.15 | 5.21 | 1.26 |
| HSG-ABS-L | 68,200 | 1.41 | 1.75 | 1.24 |
| HSG-ABS-S | 129,000 | 0.65 | 0.81 | 1.24 |
| PCB-CTRL-A | 1,800 | 24.49 | 26.54 | 1.08 |

| Origin port | Arrived | Avg transit days | Avg delay days | More than 7 days late |
|:--|--:|--:|--:|--:|
| Shenzhen | 12 | 50.3 | 8.3 | 6 |
| Houston | 3 | 28.3 | 4.3 | 1 |
| Ningbo | 5 | 43.2 | 1.2 | 1 |
| Genova | 3 | 29.0 | 1.0 | 0 |

The controller board's low multiplier is its 0 % duty; the LED panels and valves carry 20 % and 14 %. Shenzhen is where the late containers come from, which is the kind of finding the delay view exists for.

## How the numbers are computed

```
line value USD   = qty × unit price × FX (last rate on or before the invoice date)
customs value    = FOB: value + freight + insurance
                   CFR: value + insurance
                   CIF: value
duty             = customs value × duty rate of the line's NCM
statistics fee   = customs value × 3 %
local costs USD  = forwarder's ARS local costs at the ETA-date rate
landed cost      = customs value + duty + statistics fee + local costs
cash at customs  = duty + statistics fee
                   + (VAT 21 % + additional VAT 20 % + income-tax 6 % + gross-income 2.5 %)
                     × (customs value + duty + statistics fee)
```

Freight, insurance and local costs are per shipment and are spread over its lines in proportion to value. VAT and the prepayments are cash a registered business recovers, so they are reported but not added to landed cost. All rates live in one `Rates` dataclass and can be changed.

The cost logic is in [`costing.py`](src/comex_etl/costing.py) and is tested against a shipment worked out by hand (see the docstring in [`tests/test_costing.py`](tests/test_costing.py)).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                     # 62 tests
comex-etl run                 # reads data/sample, writes out/comex.db and out/import_report.xlsx
comex-etl sample              # regenerates the sample data (seeded, so it is identical every time)
```

Then query the database directly, for example:

```sql
SELECT supplier, purchases_usd, share_pct, rank_by_spend FROM v_spend_by_supplier;
SELECT * FROM data_quality_issues WHERE severity = 'reject';
```

To run it on your own files, put CSVs with the same columns in a folder and pass `--input that/folder`.

## Layout

```
src/comex_etl/
  parsing.py    pure parsers: numbers in both locales, NCM, supplier names, currencies
  extract.py    reads each export into a typed DataFrame
  validate.py   reject/warn rules, one issues table
  costing.py    FX, allocation, customs value, duty, taxes, landed cost
  load.py       SQLite tables + views (sql/views.sql)
  report.py     formatted Excel report from the views
  pipeline.py   the five steps in order
  cli.py        `comex-etl run` and `comex-etl sample`
data/sample/    fictional input files
docs/           sample report
tests/          parsers, rules, hand-worked costing, end-to-end reconciliation
```

## What is simplified

This is a portfolio project built on invented data, and it says where it cuts corners:

- **The data is fictional.** Companies, SKUs, prices, FX rates and tariff rates are made up to look plausible. The duty rates in `tariffs.csv` are planning values for the sample, not an official schedule; real rates depend on the full NCM and change.
- **The statistics fee is a flat 3 %.** The real fee has per-tier USD caps (the landed-cost calculator applies them).
- **Only FOB, CFR and CIF.** E-terms and D-terms are rejected with a clear reason rather than costed wrongly.
- **Allocation is by value.** Allocating freight by weight or volume would be better for mixed containers; the data would need those columns.
- **SQLite, not a warehouse.** The SQL is standard enough to move to Postgres or BigQuery with small changes (date functions differ).

Not legal or tax advice. Confirm rates with a customs broker.

## License

MIT
