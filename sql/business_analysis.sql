-- Phase 1 SQLite queries. Revenue and Orders refer only to synthetic sales.

-- Q01 Monthly Revenue (synthetic transactions)
SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(revenue), 2) AS synthetic_revenue
FROM sales GROUP BY month ORDER BY month;

-- Q02 Monthly Orders (one synthetic single-item order per row)
SELECT strftime('%Y-%m', order_date) AS month, COUNT(DISTINCT order_id) AS synthetic_orders
FROM sales GROUP BY month ORDER BY month;

-- Q03 Monthly Units Sold (synthetic transactions)
SELECT strftime('%Y-%m', order_date) AS month, SUM(quantity) AS units_sold
FROM sales GROUP BY month ORDER BY month;

-- Q04 Product Sales Ranking (synthetic transactions)
SELECT p.product_id, p.product_name, SUM(s.quantity) AS units_sold,
       ROUND(SUM(s.revenue), 2) AS synthetic_revenue
FROM sales s JOIN products p ON p.product_id = s.product_id
GROUP BY p.product_id, p.product_name ORDER BY synthetic_revenue DESC;

-- Q05 Category Sales Ranking (synthetic transactions)
SELECT p.category, SUM(s.quantity) AS units_sold,
       ROUND(SUM(s.revenue), 2) AS synthetic_revenue
FROM sales s JOIN products p ON p.product_id = s.product_id
GROUP BY p.category ORDER BY synthetic_revenue DESC;

-- Q06 Region Sales Ranking (synthetic transactions)
SELECT st.region, SUM(s.quantity) AS units_sold,
       ROUND(SUM(s.revenue), 2) AS synthetic_revenue
FROM sales s JOIN stores st ON st.store_id = s.store_id
GROUP BY st.region ORDER BY synthetic_revenue DESC;

-- Q07 Monthly Revenue Growth (synthetic; complete calendar months only)
WITH coverage AS (
    SELECT MIN(week_start) AS first_day,
           DATE(MAX(week_start), '+6 days') AS last_day FROM inventory
), monthly AS (
    SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS revenue
    FROM sales GROUP BY month
), marked AS (
    SELECT m.*, CASE WHEN m.month || '-01' >= c.first_day
                     AND DATE(m.month || '-01', '+1 month', '-1 day') <= c.last_day
                     THEN 1 ELSE 0 END AS is_complete_month
    FROM monthly m CROSS JOIN coverage c
), compared AS (
    SELECT *, LAG(revenue) OVER (ORDER BY month) AS previous_revenue,
           LAG(is_complete_month) OVER (ORDER BY month) AS previous_complete
    FROM marked
)
SELECT month, is_complete_month, ROUND(revenue, 2) AS synthetic_revenue,
       CASE WHEN is_complete_month = 1 AND previous_complete = 1
                 AND previous_revenue > 0
            THEN ROUND(100.0 * (revenue - previous_revenue) / previous_revenue, 2)
            ELSE NULL END AS growth_pct
FROM compared ORDER BY month;

-- Q08 Latest Inventory Level per store/product
WITH ranked AS (
    SELECT store_id, product_id, week_start, closing_stock,
           ROW_NUMBER() OVER (PARTITION BY store_id, product_id ORDER BY week_start DESC) AS rn
    FROM inventory
)
SELECT store_id, product_id, week_start, closing_stock
FROM ranked WHERE rn = 1 ORDER BY store_id, product_id;

-- Q09 Stockout Rate by weekly inventory record
SELECT COUNT(*) AS inventory_rows, SUM(stockout_flag) AS stockout_rows,
       ROUND(100.0 * AVG(stockout_flag), 2) AS stockout_rate_pct
FROM inventory;

-- Q10 Latest stock below reorder point
WITH ranked AS (
    SELECT i.*, ROW_NUMBER() OVER (PARTITION BY store_id, product_id ORDER BY week_start DESC) AS rn
    FROM inventory i
)
SELECT store_id, product_id, week_start, closing_stock, reorder_point
FROM ranked WHERE rn = 1 AND closing_stock < reorder_point
ORDER BY store_id, product_id;

-- Q11 Latest stock below safety stock
WITH ranked AS (
    SELECT i.*, ROW_NUMBER() OVER (PARTITION BY store_id, product_id ORDER BY week_start DESC) AS rn
    FROM inventory i
)
SELECT store_id, product_id, week_start, closing_stock, safety_stock
FROM ranked WHERE rn = 1 AND closing_stock < safety_stock
ORDER BY store_id, product_id;

-- Q12 Inventory by Region from latest store/product snapshots
WITH ranked AS (
    SELECT store_id, product_id, closing_stock,
           ROW_NUMBER() OVER (PARTITION BY store_id, product_id ORDER BY week_start DESC) AS rn
    FROM inventory
)
SELECT st.region, SUM(r.closing_stock) AS latest_units
FROM ranked r JOIN stores st ON st.store_id = r.store_id
WHERE r.rn = 1 GROUP BY st.region ORDER BY st.region;

-- Q13 Inventory by Category from latest store/product snapshots
WITH ranked AS (
    SELECT product_id, store_id, closing_stock,
           ROW_NUMBER() OVER (PARTITION BY store_id, product_id ORDER BY week_start DESC) AS rn
    FROM inventory
)
SELECT p.category, SUM(r.closing_stock) AS latest_units
FROM ranked r JOIN products p ON p.product_id = r.product_id
WHERE r.rn = 1 GROUP BY p.category ORDER BY p.category;

-- Q14 Monthly Units Sold from weekly inventory (grouped by week_start month)
SELECT strftime('%Y-%m', week_start) AS inventory_month, SUM(units_sold) AS units_sold
FROM inventory GROUP BY inventory_month ORDER BY inventory_month;

-- Q15 Supplier Product Count
SELECT sup.supplier_id, sup.supplier_name, COUNT(p.product_id) AS product_count
FROM suppliers sup LEFT JOIN products p ON p.supplier_id = sup.supplier_id
GROUP BY sup.supplier_id, sup.supplier_name ORDER BY sup.supplier_id;

-- Q16 Supplier Average Lead Time (static master-data attribute)
SELECT supplier_id, supplier_name, avg_lead_time_days
FROM suppliers ORDER BY supplier_id;

-- Q17 Supplier Reliability Score (static master-data attribute, not delivery history)
SELECT supplier_id, supplier_name, reliability_score
FROM suppliers ORDER BY supplier_id;

-- Q18 Stockout Rate by Supplier from weekly inventory
SELECT sup.supplier_id, sup.supplier_name, COUNT(*) AS inventory_rows,
       ROUND(100.0 * AVG(i.stockout_flag), 2) AS stockout_rate_pct
FROM inventory i JOIN suppliers sup ON sup.supplier_id = i.supplier_id
GROUP BY sup.supplier_id, sup.supplier_name ORDER BY stockout_rate_pct DESC;
