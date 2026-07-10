# Power BI Dashboard Build Guide

This project ships a single Power-BI-ready flat table
(`data/powerbi_dataset.csv`) instead of a `.pbix` file, so it stays plain-text
and diffable in Git — and so you actually build the model yourself, which is
also better for interview conversations ("walk me through how you built the
dashboard"). Follow these steps in Power BI Desktop.

## 1. Import the Data

**Get Data → Text/CSV** → select `data/powerbi_dataset.csv`.

This single file already joins store, product, and supplier attributes onto
the weekly ledger, so you don't need to build relationships between separate
tables unless you want a more "proper" star schema (optional — see step 6).

Set these column types on import:
- `week_start` → Date
- `stockout_flag` → Whole Number (used as 0/1 for rate calculations)
- everything ending in `_pct`, `_rate`, `_value`, `_cost` → Decimal Number

## 2. Core DAX Measures

Create a new Measure table (Modeling → New Table, name it `Measures`) and add:

```dax
Fill Rate % = 1 - AVERAGE(powerbi_dataset[stockout_flag])

Stockout Rate % = AVERAGE(powerbi_dataset[stockout_flag])

Total Lost Sales Value = SUM(powerbi_dataset[lost_sales_value])

Total Spoilage Cost = SUM(powerbi_dataset[spoilage_cost])

Inventory Turnover =
DIVIDE(
    SUM(powerbi_dataset[cogs]),
    AVERAGE(powerbi_dataset[inventory_value])
) * (52 / DISTINCTCOUNT(powerbi_dataset[week_start]))

Days of Inventory Outstanding = DIVIDE(365, [Inventory Turnover])

On-Time Delivery Rate = AVERAGE(powerbi_dataset[reliability_score])

Avg Lead Time (Days) = AVERAGE(powerbi_dataset[avg_lead_time_days])

Weeks Below Safety Stock =
CALCULATE(
    COUNTROWS(powerbi_dataset),
    powerbi_dataset[closing_stock] < powerbi_dataset[safety_stock],
    powerbi_dataset[stockout_flag] = 0
)
```

Format `Fill Rate %`, `Stockout Rate %`, and `On-Time Delivery Rate` as
percentages in the Measure properties pane.

## 3. Page 1 — Executive Overview

- **KPI Cards** (top row): `Fill Rate %`, `Total Lost Sales Value`,
  `Total Spoilage Cost`, `Inventory Turnover`
- **Line chart**: `Stockout Rate %` by `week_start` (weekly trend)
- **Bar chart**: `Stockout Rate %` by `category`
- **Map or bar chart**: `Stockout Rate %` by `region`
- **Slicers**: `region`, `store_type`, `category` (place on the left, sync across pages)

## 4. Page 2 — Supplier Scorecard

- **Table**: `supplier_id`, `Avg Lead Time (Days)`, `On-Time Delivery Rate`,
  `Stockout Rate %` — sorted by `Stockout Rate %` descending
- **Scatter chart**: X = `Avg Lead Time (Days)`, Y = `Stockout Rate %`,
  size = `Total Lost Sales Value`, legend = `supplier_id`
- **Callout card**: `On-Time Delivery Rate` for the worst supplier
  (use a Top N filter)

## 5. Page 3 — Inventory Health

- **Bar chart**: `Inventory Turnover` by `category`
- **Bar chart**: `Days of Inventory Outstanding` by `category`
- **Bar chart**: `Total Spoilage Cost` by `category` (highlights Perishables)
- **Table**: `product_name`, `Weeks Below Safety Stock` — sorted descending,
  to surface products that need a reorder-point review

## 6. Optional: Proper Star Schema

If you'd rather show a normalized model (closer to how this would be built
at a real company), import `stores.csv`, `products.csv`, and
`suppliers.csv` separately alongside `inventory_ledger_clean.csv` instead of
the flat file, and build these relationships in Model view:

- `inventory_ledger[store_id]` → `stores[store_id]` (many-to-one)
- `inventory_ledger[product_id]` → `products[product_id]` (many-to-one)
- `inventory_ledger[supplier_id]` → `suppliers[supplier_id]` (many-to-one)

The DAX measures above work the same way against `inventory_ledger` in this
model — just swap the table name from `powerbi_dataset` to
`inventory_ledger` and pull `region`/`store_type`/`category` from their own
tables via relationships instead of the flattened columns.

## 7. Publish

**Home → Publish** to push it to the Power BI Service, then add the
published link to your `README.md` and portfolio site so it's viewable
without opening Desktop.
