-- Analysis views over the loaded tables. SQLite dialect, kept to standard SQL
-- where possible (window functions need SQLite 3.25+).

DROP VIEW IF EXISTS v_landed_cost_by_sku;
CREATE VIEW v_landed_cost_by_sku AS
SELECT
    sku,
    MIN(description)                                  AS description,
    ncm,
    SUM(qty)                                          AS units,
    ROUND(SUM(value_usd) / SUM(qty), 4)               AS avg_price_usd,
    ROUND(SUM(landed_cost_usd) / SUM(qty), 4)         AS avg_landed_unit_usd,
    ROUND(SUM(landed_cost_usd) / SUM(value_usd), 3)   AS import_multiplier,
    ROUND(MIN(landed_unit_usd), 4)                    AS best_landed_unit_usd,
    ROUND(MAX(landed_unit_usd), 4)                    AS worst_landed_unit_usd
FROM costed_lines
GROUP BY sku, ncm;

DROP VIEW IF EXISTS v_spend_by_supplier;
CREATE VIEW v_spend_by_supplier AS
SELECT
    supplier,
    COUNT(DISTINCT shipment_id)                       AS shipments,
    ROUND(SUM(value_usd), 2)                          AS purchases_usd,
    ROUND(SUM(landed_cost_usd), 2)                    AS landed_cost_usd,
    ROUND(100.0 * SUM(value_usd)
          / (SELECT SUM(value_usd) FROM costed_lines), 1) AS share_pct,
    RANK() OVER (ORDER BY SUM(value_usd) DESC)        AS rank_by_spend
FROM costed_lines
GROUP BY supplier;

DROP VIEW IF EXISTS v_shipment_delays;
CREATE VIEW v_shipment_delays AS
SELECT
    shipment_id,
    supplier,
    origin_port,
    incoterm,
    DATE(etd)                                         AS etd,
    DATE(eta)                                         AS eta,
    DATE(arrival)                                     AS arrival,
    CAST(JULIANDAY(arrival) - JULIANDAY(etd) AS INTEGER) AS transit_days,
    CAST(JULIANDAY(arrival) - JULIANDAY(eta) AS INTEGER) AS delay_days,
    CASE
        WHEN arrival IS NULL THEN 'in transit'
        WHEN JULIANDAY(arrival) - JULIANDAY(eta) <= 0 THEN 'on time'
        WHEN JULIANDAY(arrival) - JULIANDAY(eta) <= 7 THEN 'late'
        ELSE 'very late'
    END                                               AS status
FROM shipments;

DROP VIEW IF EXISTS v_delay_by_port;
CREATE VIEW v_delay_by_port AS
SELECT
    origin_port,
    COUNT(*)                                          AS arrived,
    ROUND(AVG(transit_days), 1)                       AS avg_transit_days,
    ROUND(AVG(delay_days), 1)                         AS avg_delay_days,
    SUM(CASE WHEN delay_days > 7 THEN 1 ELSE 0 END)   AS very_late
FROM v_shipment_delays
WHERE arrival IS NOT NULL
GROUP BY origin_port;

DROP VIEW IF EXISTS v_duty_by_chapter;
CREATE VIEW v_duty_by_chapter AS
SELECT
    SUBSTR(ncm, 1, 2)                                 AS hs_chapter,
    ROUND(SUM(customs_value_usd), 2)                  AS customs_value_usd,
    ROUND(SUM(duty_usd), 2)                           AS duty_usd,
    ROUND(SUM(cash_at_customs_usd), 2)                AS cash_at_customs_usd
FROM costed_lines
GROUP BY SUBSTR(ncm, 1, 2);

DROP VIEW IF EXISTS v_monthly_imports;
CREATE VIEW v_monthly_imports AS
SELECT
    STRFTIME('%Y-%m', etd)                            AS month,
    COUNT(DISTINCT shipment_id)                       AS shipments,
    ROUND(SUM(value_usd), 2)                          AS purchases_usd,
    ROUND(SUM(landed_cost_usd), 2)                    AS landed_cost_usd,
    ROUND(SUM(SUM(landed_cost_usd)) OVER (ORDER BY STRFTIME('%Y-%m', etd)), 2)
                                                      AS cumulative_landed_usd
FROM costed_lines
GROUP BY STRFTIME('%Y-%m', etd);
