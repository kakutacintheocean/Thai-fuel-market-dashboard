-- ============================================================================
-- Thai Fuel Market: analysis queries over fact_fuel_monthly
-- Target: SQLite (data/processed/fuel_market.db), portable ANSI SQL otherwise.
-- Business question: "ความต้องการน้ำมันสำเร็จรูปแต่ละชนิดในไทยเปลี่ยนไปอย่างไร
--                      และชนิดไหนกำลังหดตัวจนกระทบแผนการผลิตของโรงกลั่น"
--
-- Table shape (one clean long table produced by scripts/clean_fuel_data.py):
--   fact_fuel_monthly(record_date, year, month, product, metric_type, quantity_million_litres, source_file)
--   metric_type = 'Consumption' (per product, EPPO) | 'Export' (total only, DOEB)
--
-- Glossary:
--   MoM (Month-over-Month): this month's value vs. the immediately previous month.
--   YoY (Year-over-Year):   this month's value vs. the same month one year earlier.
--   Both are computed with the LAG() window function below: LAG(x, 1) looks back
--   one row (one month) for MoM, LAG(x, 12) looks back twelve rows (twelve months) for YoY.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1) Monthly consumption by product with MoM and YoY growth (LAG window fn)
--    -> feeds the "trend by product" line chart and the growth-rate chart
-- ----------------------------------------------------------------------------
SELECT
    f.product,
    f.record_date,
    f.year,
    f.month,
    f.quantity_million_litres                                                         AS qty_million_litres,
    LAG(f.quantity_million_litres, 1)  OVER (PARTITION BY f.product ORDER BY f.record_date) AS qty_prev_month,
    LAG(f.quantity_million_litres, 12) OVER (PARTITION BY f.product ORDER BY f.record_date) AS qty_same_month_last_year,
    ROUND(
        100.0 * (f.quantity_million_litres - LAG(f.quantity_million_litres, 1) OVER (PARTITION BY f.product ORDER BY f.record_date))
        / LAG(f.quantity_million_litres, 1) OVER (PARTITION BY f.product ORDER BY f.record_date)
    , 2)                                                                               AS mom_growth_pct,
    ROUND(
        100.0 * (f.quantity_million_litres - LAG(f.quantity_million_litres, 12) OVER (PARTITION BY f.product ORDER BY f.record_date))
        / LAG(f.quantity_million_litres, 12) OVER (PARTITION BY f.product ORDER BY f.record_date)
    , 2)                                                                               AS yoy_growth_pct
FROM fact_fuel_monthly f
WHERE f.metric_type = 'Consumption'
ORDER BY f.product, f.record_date;


-- ----------------------------------------------------------------------------
-- 2) Yearly consumption by product (GROUP BY) with YoY growth on the annual total
--    -> feeds the KPI cards ("ปีนี้เทียบปีก่อน")
-- ----------------------------------------------------------------------------
WITH yearly AS (
    SELECT
        product,
        year,
        SUM(quantity_million_litres) AS qty_year_million_litres
    FROM fact_fuel_monthly
    WHERE metric_type = 'Consumption'
    GROUP BY product, year
)
SELECT
    product,
    year,
    qty_year_million_litres,
    LAG(qty_year_million_litres, 1) OVER (PARTITION BY product ORDER BY year) AS qty_prev_year,
    ROUND(
        100.0 * (qty_year_million_litres - LAG(qty_year_million_litres, 1) OVER (PARTITION BY product ORDER BY year))
        / LAG(qty_year_million_litres, 1) OVER (PARTITION BY product ORDER BY year)
    , 2) AS yoy_growth_pct
FROM yearly
ORDER BY product, year;


-- ----------------------------------------------------------------------------
-- 3) Shrinking products: products with 3+ consecutive months of negative YoY
--    growth, most recent run first -> answers "ชนิดไหนกำลังหดตัว"
-- ----------------------------------------------------------------------------
WITH growth AS (
    SELECT
        product,
        record_date,
        quantity_million_litres,
        LAG(quantity_million_litres, 12) OVER (PARTITION BY product ORDER BY record_date) AS qty_last_year,
        ROUND(
            100.0 * (quantity_million_litres - LAG(quantity_million_litres, 12) OVER (PARTITION BY product ORDER BY record_date))
            / LAG(quantity_million_litres, 12) OVER (PARTITION BY product ORDER BY record_date)
        , 2) AS yoy_growth_pct
    FROM fact_fuel_monthly
    WHERE metric_type = 'Consumption'
),
flagged AS (
    SELECT *,
        CASE WHEN yoy_growth_pct < 0 THEN 1 ELSE 0 END AS is_shrinking
    FROM growth
    WHERE qty_last_year IS NOT NULL
),
streaks AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY product ORDER BY record_date)
        - ROW_NUMBER() OVER (PARTITION BY product, is_shrinking ORDER BY record_date) AS streak_group
    FROM flagged
)
SELECT
    product,
    MIN(record_date) AS streak_start,
    MAX(record_date) AS streak_end,
    COUNT(*)         AS consecutive_months_shrinking,
    ROUND(AVG(yoy_growth_pct), 2) AS avg_yoy_growth_pct
FROM streaks
WHERE is_shrinking = 1
GROUP BY product, streak_group
HAVING COUNT(*) >= 3
ORDER BY streak_end DESC, consecutive_months_shrinking DESC;


-- ----------------------------------------------------------------------------
-- 4) JOIN: total monthly consumption vs total monthly export, with export
--    share of consumption -> answers "ส่งออกกินส่วนแบ่งจาก supply เท่าไหร่"
-- ----------------------------------------------------------------------------
WITH monthly_consumption AS (
    SELECT record_date, year, month, SUM(quantity_million_litres) AS consumption_total
    FROM fact_fuel_monthly
    WHERE metric_type = 'Consumption'
    GROUP BY record_date, year, month
),
monthly_export AS (
    SELECT record_date, year, month, quantity_million_litres AS export_total
    FROM fact_fuel_monthly
    WHERE metric_type = 'Export'
)
SELECT
    c.record_date,
    c.year,
    c.month,
    c.consumption_total,
    e.export_total,
    ROUND(100.0 * e.export_total / c.consumption_total, 2) AS export_pct_of_consumption,
    LAG(e.export_total, 12) OVER (ORDER BY c.record_date)  AS export_same_month_last_year,
    ROUND(
        100.0 * (e.export_total - LAG(e.export_total, 12) OVER (ORDER BY c.record_date))
        / LAG(e.export_total, 12) OVER (ORDER BY c.record_date)
    , 2) AS export_yoy_growth_pct
FROM monthly_consumption c
JOIN monthly_export e
    ON e.record_date = c.record_date
ORDER BY c.record_date;


-- ----------------------------------------------------------------------------
-- 5) KPI snapshot for the latest available month (dashboard KPI cards)
--    total consumption, YoY growth, and the biggest-shrinking product
-- ----------------------------------------------------------------------------
WITH latest AS (
    SELECT MAX(record_date) AS max_date FROM fact_fuel_monthly WHERE metric_type = 'Consumption'
),
per_product AS (
    SELECT
        product,
        record_date,
        quantity_million_litres,
        LAG(quantity_million_litres, 12) OVER (PARTITION BY product ORDER BY record_date) AS qty_last_year
    FROM fact_fuel_monthly
    WHERE metric_type = 'Consumption'
)
SELECT
    p.product,
    p.record_date,
    p.quantity_million_litres                                  AS qty_this_month,
    p.qty_last_year,
    ROUND(100.0 * (p.quantity_million_litres - p.qty_last_year) / p.qty_last_year, 2) AS yoy_growth_pct
FROM per_product p
JOIN latest l ON p.record_date = l.max_date
ORDER BY yoy_growth_pct ASC;
