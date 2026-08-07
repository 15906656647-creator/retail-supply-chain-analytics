-- ============================================================
-- Retail Inventory & Supply Chain Analytics — SQL
-- Works with SQL / PostgreSQL / MySQL (minor syntax tweaks
-- may be needed for date functions depending on engine)
-- ============================================================

-- ---------- SCHEMA ----------
CREATE TABLE IF NOT EXISTS stores (
    store_id      TEXT PRIMARY KEY,
    store_name    TEXT,
    region        TEXT,
    store_type    TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT,
    category      TEXT,
    unit_cost     NUMERIC,
    unit_price    NUMERIC,
    supplier_id   TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id         TEXT PRIMARY KEY,
    supplier_name       TEXT,
    category            TEXT,
    avg_lead_time_days  INTEGER,
    reliability_score   NUMERIC
);

CREATE TABLE IF NOT EXISTS inventory_ledger (
    store_id          TEXT,
    product_id        TEXT,
    category          TEXT,
    week_start        DATE,
    opening_stock     INTEGER,
    units_received    INTEGER,
    spoilage_units    INTEGER,
    units_sold        INTEGER,
    closing_stock     INTEGER,
    stockout_flag     INTEGER,
    lost_sales_units  INTEGER,
    reorder_point     INTEGER,
    safety_stock      INTEGER,
    supplier_id       TEXT
);

-- Load data/inventory_ledger_clean.csv, data/stores.csv, data/products.csv,
-- data/suppliers.csv into these tables before running queries.
-- Example (SQL CLI):
--   SQL3 supply_chain.db
--   .mode csv
--   .import data/inventory_ledger_clean.csv inventory_ledger
--   .import data/stores.csv stores
--   .import data/products.csv products
--   .import data/suppliers.csv suppliers

-- ============================================================
-- BUSINESS QUESTIONS
-- ============================================================

-- Q1. Overall fill rate and stockout rate
SELECT
    ROUND(100.0 * (1 - AVG(stockout_flag)), 2) AS fill_rate_pct,
    ROUND(100.0 * AVG(stockout_flag), 2)       AS stockout_rate_pct
FROM inventory_ledger;

-- Q2. Stockout rate by category
SELECT
    category,
    COUNT(*)                                    AS total_weeks,
    SUM(stockout_flag)                          AS stockout_weeks,
    ROUND(100.0 * AVG(stockout_flag), 2)        AS stockout_rate_pct
FROM inventory_ledger
GROUP BY category
ORDER BY stockout_rate_pct DESC;

-- Q3. Stockout rate by region (join to stores)
SELECT
    s.region,
    ROUND(100.0 * AVG(il.stockout_flag), 2) AS stockout_rate_pct
FROM inventory_ledger il
JOIN stores s ON il.store_id = s.store_id
GROUP BY s.region
ORDER BY stockout_rate_pct DESC;

-- Q4. Top 10 products by lost sales value (price * lost units)
SELECT
    p.product_name,
    il.category,
    SUM(il.lost_sales_units)                                AS total_lost_units,
    ROUND(SUM(il.lost_sales_units * p.unit_price), 2)       AS total_lost_sales_value
FROM inventory_ledger il
JOIN products p ON il.product_id = p.product_id
GROUP BY p.product_name, il.category
ORDER BY total_lost_sales_value DESC
LIMIT 10;

-- Q5. Supplier scorecard: lead time, reliability, and resulting stockout rate
SELECT
    sup.supplier_id,
    sup.supplier_name,
    sup.avg_lead_time_days,
    sup.reliability_score,
    ROUND(100.0 * AVG(il.stockout_flag), 2) AS stockout_rate_pct
FROM inventory_ledger il
JOIN suppliers sup ON il.supplier_id = sup.supplier_id
GROUP BY sup.supplier_id, sup.supplier_name, sup.avg_lead_time_days, sup.reliability_score
ORDER BY stockout_rate_pct DESC;

-- Q6. Weeks below safety stock (early-warning signal, not yet a stockout)
SELECT
    store_id,
    product_id,
    week_start,
    closing_stock,
    safety_stock
FROM inventory_ledger
WHERE closing_stock < safety_stock AND stockout_flag = 0
ORDER BY week_start DESC
LIMIT 20;

-- Q7. Total spoilage cost by category (perishables focus)
SELECT
    il.category,
    SUM(il.spoilage_units)                              AS total_spoiled_units,
    ROUND(SUM(il.spoilage_units * p.unit_cost), 2)       AS total_spoilage_cost
FROM inventory_ledger il
JOIN products p ON il.product_id = p.product_id
GROUP BY il.category
ORDER BY total_spoilage_cost DESC;

-- Q8. Monthly stockout trend (is it getting better or worse over time?)
SELECT
    strftime('%Y-%m', week_start) AS month,
    ROUND(100.0 * AVG(stockout_flag), 2) AS stockout_rate_pct
FROM inventory_ledger
GROUP BY month
ORDER BY month;

-- Q9. Store-type performance: fill rate and avg inventory value
SELECT
    s.store_type,
    ROUND(100.0 * (1 - AVG(il.stockout_flag)), 2)              AS fill_rate_pct,
    ROUND(AVG(il.closing_stock * p.unit_cost), 2)              AS avg_inventory_value
FROM inventory_ledger il
JOIN stores s ON il.store_id = s.store_id
JOIN products p ON il.product_id = p.product_id
GROUP BY s.store_type
ORDER BY fill_rate_pct DESC;

-- Q10. Products with the highest reorder frequency (closing stock repeatedly below reorder point)
SELECT
    p.product_name,
    il.category,
    COUNT(*) AS weeks_below_reorder_point
FROM inventory_ledger il
JOIN products p ON il.product_id = p.product_id
WHERE il.closing_stock < il.reorder_point
GROUP BY p.product_name, il.category
ORDER BY weeks_below_reorder_point DESC
LIMIT 10;
