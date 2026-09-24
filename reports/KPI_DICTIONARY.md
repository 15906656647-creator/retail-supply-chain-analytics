# KPI Dictionary

All monetary values use the dataset's synthetic currency units. CSV ratios are proportions from 0 to 1; MoM growth is a signed proportion. Missing denominators produce blank CSV cells.

Complete calendar months are determined from contiguous inventory-week coverage, not from the presence of an order on every day. Complete: 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12. Partial: 2025-01, 2026-01.

| KPI Name | Business Meaning | Source Table | Formula | Grain | Caveat / Limitation |
|---|---|---|---|---|---|
| Synthetic Revenue | Generated sales value | sales | SUM(revenue) | all sales or selected dimension | Transaction prices include synthetic discounts. |
| Synthetic Orders | Generated single-item orders | sales | COUNT(DISTINCT order_id) | all sales or selected dimension | One order_id is one product row, not a customer basket. |
| Units Sold | Sold units | sales; inventory | SUM(sales.quantity) | all sales or selected dimension | Reconciles to SUM(inventory.units_sold). |
| Synthetic AOV Proxy | Value per generated order | sales | Synthetic Revenue / Synthetic Orders | all sales, region, store or month | Synthetic average single-item order value; not customer basket AOV. |
| Synthetic Average Selling Price | Generated value per unit | sales | Synthetic Revenue / Units Sold | all sales or selected dimension | Includes generated 0–5% discounts. |
| Stockout Rate | Share of weekly records flagged stockout | inventory | SUM(stockout_flag) / COUNT(records) | week × store × product, then selected dimension | Record-based; not closing_stock = 0 or an order fill rate. |
| Record-Based Fill Rate Proxy | Complement of record stockout rate | inventory | 1 - Stockout Rate | all weekly inventory records | Not actual order fulfillment. |
| Lost Sales Units | Estimated unserved units | inventory | SUM(lost_sales_units) | weekly inventory records | Synthetic estimate. |
| Estimated Lost Sales Value | Catalog-price value of estimated lost units | inventory; products | SUM(lost_sales_units × unit_price) | weekly inventory records | Estimate uses catalog price, not transaction price. |
| Spoilage Units | Recorded spoiled units | inventory | SUM(spoilage_units) | weekly inventory records | Synthetic inventory. |
| Estimated Spoilage Cost | Cost estimate of spoiled units | inventory; products | SUM(spoilage_units × unit_cost) | weekly inventory records | Uses synthetic master unit cost. |
| Estimated COGS | Cost estimate of units sold | inventory; products | SUM(units_sold × unit_cost) | weekly inventory records | Not audited COGS. |
| Approx Inventory Turnover | Analytical stock turnover proxy | inventory; products | Estimated COGS / MEAN(weekly SUM(closing_stock × unit_cost)) | all observed weeks by dimension | Weekly closing values and synthetic costs; not audited financial turnover. |
| Synthetic Revenue Share | Dimension share of generated value | sales | Dimension Synthetic Revenue / Overall Synthetic Revenue | category or region | All observed sales, including partial edge months. |
| Units Share | Category share of sold units | sales | Category Units Sold / Overall Units Sold | category | All observed sales. |
| Revenue MoM Growth | Change between adjacent complete calendar months | sales; inventory coverage | (current revenue - previous revenue) / previous revenue | month | NULL for partial months, first complete month, or zero denominator. |
| Units MoM Growth | Change between adjacent complete calendar months | sales; inventory coverage | (current units - previous units) / previous units | month | Same completeness and denominator rule. |
| Latest Inventory Units | Latest recorded stock | inventory | SUM(latest closing_stock by store_id + product_id) | store or region | Weekly closing snapshot. |
| Latest Inventory Value | Cost value of latest stock | inventory; products | SUM(latest closing_stock × unit_cost) | store or region | Synthetic master cost. |
| Supplier Product Count | Catalog products linked to supplier | products | COUNT(product_id) | supplier | Product master count, not procurement volume. |
| Supplier Lead Time | Master-data average lead time | suppliers | avg_lead_time_days | supplier | Static synthetic attribute; no delivery history. |
| Supplier Reliability Score | Master-data reliability score | suppliers | reliability_score | supplier | Static synthetic attribute; not calculated from purchase transactions. |
| Complete Month Flag | Calendar month fully covered by inventory weeks | inventory.week_start | All calendar days lie within contiguous observed inventory-week coverage | month | An observed sales date alone does not prove full coverage. |
| Revenue and Units Rank | Product position by revenue or units | sales | Descending rank with minimum rank for ties | product | Based on synthetic sales. |

Sales and inventory are aggregated independently before dimensional merging. Supplier stockout association does not establish supplier causation. Inventory accounting semantics for receipts and opening stock remain unresolved.
