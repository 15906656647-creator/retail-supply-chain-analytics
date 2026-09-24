# Power BI Dashboard Build Guide — Phase 5

## 1. Purpose and required files

This is a **Power BI-ready data layer and build guide**, not a completed Phase 5
`.pbix`. Run `python -m src.powerbi_dataset` at the repository root first. The
command validates Phase 1–4 inputs, reconciles their metrics, and writes
`data/processed/powerbi_business_dataset.csv`. A tracked
`retail-supply-chain-dashboard.pbix` belongs to the original project; it is not
the five-page model described here.

Import these CSVs with **Home → Get data → Text/CSV → Transform Data** and give
the queries these exact names:

| Model table | File | Business grain / unique key |
|---|---|---|
| `FactSales` | `data/processed/powerbi_business_dataset.csv` | One synthetic single-item order / `order_id` |
| `FactInventory` | `data/processed/inventory_clean.csv` | One inventory week × store × product / `week_start, store_id, product_id` |
| `FactForecastEvaluation` | `data/processed/forecast_results.csv` | One historical test week × store × product / `date, store_id, product_id` |
| `FactAlerts` | `data/processed/inventory_alerts.csv` | One future forecast date × store × product / `forecast_date, store_id, product_id` |
| `DimStore` | `data/raw/stores.csv` | One store / `store_id` |
| `DimProduct` | `data/raw/products.csv` | One product / `product_id` |
| `DimSupplier` | `data/raw/suppliers.csv` | One supplier / `supplier_id` |

`data/processed/latest_inventory_snapshot.csv`, `overall_kpi.csv`, and
`monthly_kpi.csv` are validation references, not additional model facts. The
generator checks that `FactAlerts[current_stock]` equals the latest snapshot's
`closing_stock` for each store/product pair. Do not also import the old
`data/powerbi_dataset.csv`: it is an unrelated legacy dataset.

## 2. Table grain and metric meaning

`FactSales` is a dimension-enriched order fact. Its 19 columns are
`order_id`, `order_date`, `week_start`, `store_id`, `store_name`, `region`,
`store_type`, `product_id`, `product_name`, `category`, `supplier_id`,
`supplier_name`, `avg_lead_time_days`, `reliability_score`, `quantity`,
`catalog_unit_price`, `transaction_unit_price`, `revenue`, and
`synthetic_flag`. Descriptive columns are repeated per order solely for
standalone CSV use. In the semantic model, use the dimension tables for labels
and slicers; hide those duplicate descriptive columns on `FactSales` after
creating the relationships.

Sales `order_date` is the generated transaction date inside its source
inventory week. Inventory `week_start` is always a Monday. A calendar month of
daily sales is **not** identical to the inventory weeks whose Mondays fall in
that month. `FactForecastEvaluation[date]` refers to a historical holdout week
with known actual demand. `FactAlerts[forecast_date]` is a genuine prototype
forecast for the week after the latest observed inventory week. They must not
be added together or labeled as the same forecast series.

The main CSV contains no inventory, forecast, or alert measures. Its
`order_id` remains unique after only `many_to_one` joins to the dimensions.
Never connect sales rows to weekly inventory by only store and product; that
would multiply both facts. Do not repair such a join with `DISTINCT`, `MAX`,
or complex DAX.

## 3. Import types and model relationships

In Power Query, set `order_date`, `week_start`, `date`, `forecast_date`, and
`inventory_week_start` to **Date**. Set IDs, names, category, region,
`risk_status`, and `risk_reason` to **Text**; keep leading zeros in IDs.
Set quantities, stock counts, flags, lead time, `reorder_point`, and
`safety_stock` to **Whole Number** where applicable. Set `revenue`, sales
prices, and `DimProduct[unit_cost]` to **Fixed Decimal Number** for currency
totals. Set `reliability_score`, forecast values, average demand, projected
stock, and `weeks_of_supply` to **Decimal Number**. `units_received_clean` has 515
legitimate blanks; do not replace them with zero. `synthetic_flag` and
`stockout_flag` are 0/1 whole numbers.

In **Model view**, remove any unwanted automatically detected relationships
and create the following active **one-to-many, single direction** links. The
arrow indicates filter flow from the unique key to the many-side foreign key.

| One side → many side | Purpose |
|---|---|
| `DimStore[store_id]` → each fact's `[store_id]` | Store and region filters |
| `DimProduct[product_id]` → each fact's `[product_id]` | Product and category filters |
| `DimSupplier[supplier_id]` → `DimProduct[supplier_id]` | Supplier filters flow through products |
| `DimDate[Date]` → `FactSales[order_date]` | Daily synthetic sales |
| `DimDate[Date]` → `FactInventory[week_start]` | Weekly inventory by starting Monday |
| `DimDate[Date]` → `FactForecastEvaluation[date]` | Historical test weeks |
| `DimDate[Date]` → `FactAlerts[forecast_date]` | Future alert week |

Each relationship must be **Active**, cardinality **One to many (1:*)**, and
cross-filter direction **Single**. Do not create direct fact-to-fact,
many-to-many, bidirectional, or extra `DimSupplier`-to-fact links. The
`supplier_id` and descriptive columns already present in some facts are useful
for source validation, not additional relationship paths. Hide them in report
view after model setup. [Microsoft's star schema guidance](https://learn.microsoft.com/power-bi/guidance/star-schema)
explains the unique dimension-key and fact-grain pattern.

## 4. Date table

After the seven CSV tables are loaded and date types are set, select
**Modeling → New table** and paste this calculated **table**. Its complete-month
flag follows Phase 2's contiguous inventory-week coverage: January 2025 and
January 2026 are partial in the current inputs. The Python generator rejects
gaps in that weekly coverage.

```dax
DimDate =
VAR FirstSalesDate = MINX ( ALL ( FactSales ), FactSales[order_date] )
VAR LastAlertDate = MAXX ( ALL ( FactAlerts ), FactAlerts[forecast_date] )
VAR FirstInventoryWeek = MINX ( ALL ( FactInventory ), FactInventory[week_start] )
VAR LastInventoryDay = MAXX ( ALL ( FactInventory ), FactInventory[week_start] ) + 6
RETURN
    ADDCOLUMNS (
        CALENDAR ( FirstSalesDate, LastAlertDate ),
        "Year", YEAR ( [Date] ),
        "Quarter", "Q" & QUARTER ( [Date] ),
        "Month Number", MONTH ( [Date] ),
        "Month Name", FORMAT ( [Date], "MMMM" ),
        "Year Month", FORMAT ( [Date], "yyyy-MM" ),
        "Year Month Sort", YEAR ( [Date] ) * 100 + MONTH ( [Date] ),
        "Month Start", DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 ),
        "Week Number", WEEKNUM ( [Date], 21 ),
        "Is Complete Month",
            DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 ) >= FirstInventoryWeek
                && EOMONTH ( [Date], 0 ) <= LastInventoryDay
    )
```

Mark `DimDate` as a date table using `DimDate[Date]` (**Table tools → Mark as
date table**). Set `Month Name` to **Sort by column → Month Number** and
`Year Month` to **Sort by column → Year Month Sort**. Use `Year Month` on monthly
axes, never a standalone text month. [Microsoft's date-table instructions](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-date-tables)
cover the Desktop operation.

## 5. DAX measures

The following are **measures**, created one definition at a time with
**Modeling → New measure**;
`DimDate` above is the only calculated table. Use the model table names from
section 1. Format currency, whole-number counts, ratios, and percentages in
Measure tools. Measures respond to dimension filters; static supplier fields
do not become observed delivery performance.

```dax
Revenue = SUM ( FactSales[revenue] )

Orders = DISTINCTCOUNT ( FactSales[order_id] )

Units Sold = SUM ( FactSales[quantity] )

Average Order Value = DIVIDE ( [Revenue], [Orders] )

Average Selling Price = DIVIDE ( [Revenue], [Units Sold] )

Inventory Records = COUNTROWS ( FactInventory )

Stockout Records = SUM ( FactInventory[stockout_flag] )

Stockout Rate = DIVIDE ( [Stockout Records], [Inventory Records] )

Fill Rate = IF ( NOT ISBLANK ( [Stockout Rate] ), 1 - [Stockout Rate] )

Estimated COGS =
    SUMX ( FactInventory, FactInventory[units_sold] * RELATED ( DimProduct[unit_cost] ) )

Weekly Closing Inventory Value =
    SUMX ( FactInventory, FactInventory[closing_stock] * RELATED ( DimProduct[unit_cost] ) )

Inventory Turnover =
    DIVIDE (
        [Estimated COGS],
        AVERAGEX (
            VALUES ( FactInventory[week_start] ),
            CALCULATE ( [Weekly Closing Inventory Value] )
        )
    )

Current Inventory = SUM ( FactAlerts[current_stock] )

Inventory Snapshot Week = MAX ( FactAlerts[inventory_week_start] )

Alert Forecast Week = MAX ( FactAlerts[forecast_date] )

Inventory Value =
    SUMX ( FactAlerts, FactAlerts[current_stock] * RELATED ( DimProduct[unit_cost] ) )

Forecast Demand = SUM ( FactAlerts[forecast_demand] )

Alert Count = COUNTROWS ( FactAlerts )

Stockout Risk Count =
    CALCULATE ( [Alert Count], KEEPFILTERS ( FactAlerts[risk_status] = "STOCKOUT_RISK" ) )

Low Stock Count =
    CALCULATE ( [Alert Count], KEEPFILTERS ( FactAlerts[risk_status] = "LOW_STOCK" ) )

Overstock Count =
    CALCULATE ( [Alert Count], KEEPFILTERS ( FactAlerts[risk_status] = "OVERSTOCK" ) )

Normal Count =
    CALCULATE ( [Alert Count], KEEPFILTERS ( FactAlerts[risk_status] = "NORMAL" ) )

Supplier Reliability = AVERAGE ( DimSupplier[reliability_score] )

Average Lead Time = AVERAGE ( DimSupplier[avg_lead_time_days] )

Supplier Product Count = DISTINCTCOUNT ( DimProduct[product_id] )

Actual Demand = SUM ( FactForecastEvaluation[actual_demand] )

Naive Prediction = SUM ( FactForecastEvaluation[naive_prediction] )

Linear Regression Prediction = SUM ( FactForecastEvaluation[linear_regression_prediction] )

Random Forest Prediction = SUM ( FactForecastEvaluation[random_forest_prediction] )

Random Forest MAE =
    AVERAGEX (
        FactForecastEvaluation,
        ABS (
            FactForecastEvaluation[actual_demand]
                - FactForecastEvaluation[random_forest_prediction]
        )
    )

Random Forest RMSE =
    SQRT (
        AVERAGEX (
            FactForecastEvaluation,
            POWER (
                FactForecastEvaluation[actual_demand]
                    - FactForecastEvaluation[random_forest_prediction],
                2
            )
        )
    )
```

`Inventory Turnover` matches Phase 2's **approximate** `estimated COGS ÷
mean weekly closing inventory value`, using synthetic catalog cost. It is
meaningful over the selected weekly records, not as audited financial turnover.
`Current Inventory` is one latest observed snapshot carried into the single
future alert date; never sum historical `closing_stock` and call that current.
`Fill Rate` is the complement of the weekly-record stockout rate, not an order
fulfillment rate. `Supplier Reliability` is an average of static supplier
master scores; it is not an on-time delivery rate.

For month-on-month revenue, create this measure and use it only at a **single
month** context. It removes the current date filter to calculate both full
calendar months while preserving Store, Product, Category, Region, and Supplier
filters. The two adjacent months must both have complete inventory coverage;
zero prior revenue returns blank. February 2025 is blank because January 2025
is partial, even though February itself is complete.

```dax
MoM Revenue Growth =
VAR CurrentMonth = SELECTEDVALUE ( DimDate[Month Start] )
VAR CurrentComplete = SELECTEDVALUE ( DimDate[Is Complete Month], FALSE () )
VAR PreviousMonth = EDATE ( CurrentMonth, -1 )
VAR PreviousComplete =
    CALCULATE (
        SELECTEDVALUE ( DimDate[Is Complete Month], FALSE () ),
        FILTER ( ALL ( DimDate ), DimDate[Date] = PreviousMonth )
    )
VAR CurrentRevenue =
    CALCULATE (
        [Revenue],
        FILTER (
            ALL ( DimDate ),
            DimDate[Date] >= CurrentMonth
                && DimDate[Date] <= EOMONTH ( CurrentMonth, 0 )
        )
    )
VAR PreviousRevenue =
    CALCULATE (
        [Revenue],
        FILTER (
            ALL ( DimDate ),
            DimDate[Date] >= PreviousMonth
                && DimDate[Date] <= EOMONTH ( PreviousMonth, 0 )
        )
    )
RETURN
    IF (
        NOT ISBLANK ( CurrentMonth )
            && CurrentComplete
            && PreviousComplete
            && PreviousRevenue > 0,
        DIVIDE ( CurrentRevenue - PreviousRevenue, PreviousRevenue )
    )

Latest Selected Complete Month MoM =
VAR LatestMonth =
    MAXX (
        FILTER (
            VALUES ( DimDate[Month Start] ),
            CALCULATE ( SELECTEDVALUE ( DimDate[Is Complete Month], FALSE () ) )
        ),
        DimDate[Month Start]
    )
RETURN
    IF (
        NOT ISBLANK ( LatestMonth ),
        CALCULATE (
            [MoM Revenue Growth],
            KEEPFILTERS ( DimDate[Month Start] = LatestMonth )
        )
    )
```

The card measure picks the latest complete month in the current Date slicer;
it is blank if that month lacks an eligible prior complete month. Use the
single-month `MoM Revenue Growth` on a `Year Month` chart axis. Format both as
percentages. The cumulative Revenue card includes all selected sales, while
MoM deliberately excludes partial-month comparisons.

## 6. Page 1 — Executive Overview

Default the `DimDate[Year Month]` slicer to February–December 2025 for a
comparable trend; clear it when checking the all-period Phase 2 totals.

| Visual / type | Axis or rows | Values | Legend / visual filter |
|---|---|---|---|
| KPI cards | — | `[Revenue]`, `[Orders]`, `[Units Sold]`, `[Latest Selected Complete Month MoM]`, `[Stockout Rate]` | Labels must say synthetic sales and weekly-record stockout |
| Revenue Trend / line | `DimDate[Year Month]` | `[Revenue]` | Sort by `Year Month Sort`; complete months only for comparison |
| Sales by Region / clustered bar | `DimStore[region]` | `[Revenue]` | Descending revenue; no legend |
| Sales by Category / clustered bar | `DimProduct[category]` | `[Revenue]` | Descending revenue; no legend |

Slicers: `DimDate[Year Month]`, `DimStore[region]`, and
`DimProduct[category]`. Add `DimStore[store_name]` only if a store-level
analysis is needed. The Date slicer filters inventory by **week start**, while
sales use the actual order date; label those different date meanings.

## 7. Page 2 — Sales Performance

| Visual / type | Axis or rows | Values | Legend / visual filter |
|---|---|---|---|
| Revenue Trend / line | `DimDate[Year Month]` | `[Revenue]` | Complete months for comparable monthly trend |
| Product Ranking / horizontal bar | `DimProduct[product_name]` | `[Revenue]` | Top 10 by `[Revenue]`, descending |
| Category Ranking / horizontal bar | `DimProduct[category]` | `[Revenue]` | Descending |
| Regional Revenue / clustered column | `DimStore[region]` | `[Revenue]` | No legend; synthetic currency axis |
| Regional Units / clustered column | `DimStore[region]` | `[Units Sold]` | No legend; unit-count axis |
| Monthly Growth / line | `DimDate[Year Month]` | `[MoM Revenue Growth]` | Percentage axis; February 2025 and partial months blank |

For Top N: select Product Ranking → **Filters on this visual** →
`product_name` → **Top N** → enter `10` → drag `[Revenue]` to **By value** →
**Apply filter**, then sort by `[Revenue]` descending. Use slicers
`DimDate[Year Month]`, `DimStore[region]`, `DimStore[store_name]`,
`DimProduct[category]`, and `DimProduct[product_name]` only when needed;
prioritize Date, Region, and Product in the visible layout.

## 8. Page 3 — Inventory Health

| Visual / type | Axis or rows | Values | Legend / visual filter |
|---|---|---|---|
| Current Inventory / card | — | `[Current Inventory]` | Adjacent date card: `[Inventory Snapshot Week]` |
| Inventory Turnover / card | — | `[Inventory Turnover]` | Approximate synthetic-cost ratio over selected historical weeks |
| Stockout Rate / card | — | `[Stockout Rate]` | Weekly-record rate |
| Risk Status Distribution / bar | `FactAlerts[risk_status]` | `[Alert Count]` | Keep status text visible |
| Stock and thresholds / table | `DimStore[store_name]`, `DimProduct[product_name]` | `FactAlerts[current_stock]`, `FactAlerts[safety_stock]`, `FactAlerts[reorder_point]`, `FactAlerts[weeks_of_supply]`, `FactAlerts[risk_status]`, `FactAlerts[risk_reason]` | Each alert is one store/product, so select **Don't summarize** for row fields |

Slicers: `DimStore[region]`, `DimStore[store_name]`,
`DimProduct[category]`, and `FactAlerts[risk_status]`. Use **Format → Edit
interactions** so the Risk Status slicer filters the current-snapshot card,
risk chart, and table, but does **not** filter historical Stockout Rate or
Inventory Turnover. The single-direction model will not send an alert status
filter into `FactInventory`; do not add a fact-to-fact relationship to force
one. Do not sync a historical Date slicer to the current-snapshot visuals.

## 9. Page 4 — Supplier Performance

| Visual / type | Axis or rows | Values | Legend / visual filter |
|---|---|---|---|
| Average Lead Time / card | — | `[Average Lead Time]` | Days; static synthetic master attribute |
| Reliability / card | — | `[Supplier Reliability]` | Static synthetic score, not observed delivery success |
| Associated Stockout Rate / card | — | `[Stockout Rate]` | Weekly records associated with selected suppliers' products |
| Supplier Ranking / table | `DimSupplier[supplier_name]` | `[Supplier Product Count]`, `[Average Lead Time]`, `[Supplier Reliability]`, `[Stockout Rate]` | Sort by `[Stockout Rate]` descending; filter blank product counts |
| Lead Time vs Stockout / scatter | X: `[Average Lead Time]`; Details: `DimSupplier[supplier_name]` | Y: `[Stockout Rate]`; Size: `[Supplier Product Count]` | No causal interpretation |

Slicers: `DimSupplier[supplier_name]` and `DimProduct[category]`. Category
filters the supplier's linked products and historical stockout records; a
supplier's master reliability and lead-time values themselves do not change
by category. **Supplier-associated stockout is not supplier-caused stockout.**
There are no delivery transactions from which to calculate an actual on-time
delivery rate.

## 10. Page 5 — Forecast & Alerts

Place two clearly titled sections on this page. The historical chart is a
model **holdout evaluation** for dates in `FactForecastEvaluation`, whereas
the alert section uses one **next-week prototype forecast date**.

| Visual / type | Axis or rows | Values | Legend / visual filter |
|---|---|---|---|
| Historical Actual vs Forecast / line | `DimDate[Date]` | `[Actual Demand]`, `[Naive Prediction]`, `[Random Forest Prediction]` | Measure names form legend; historical test weeks only |
| Historical Error / cards | — | `[Random Forest MAE]`, `[Random Forest RMSE]` | Units per store/product/week; do not relabel as future accuracy |
| Risk Status Distribution / bar | `FactAlerts[risk_status]` | `[Alert Count]` | Status text visible |
| High Risk Table / table | `DimStore[store_name]`, `DimProduct[product_name]` | `FactAlerts[current_stock]`, `FactAlerts[forecast_demand]`, `FactAlerts[risk_status]`, `FactAlerts[risk_reason]` | Filter `risk_status` to `STOCKOUT_RISK` and `LOW_STOCK`; Don't summarize row fields |
| Forecast vs Current Stock / clustered bar | `DimProduct[product_name]` | `[Forecast Demand]`, `[Current Inventory]` | Top 10 by `[Forecast Demand]`; for multiple stores aggregate at product level |

Slicers: `DimStore[store_name]`, `DimProduct[product_name]`, and
`FactAlerts[risk_status]`. An optional `FactForecastEvaluation[date]` slicer
may filter only the historical visuals; use **Edit interactions** to disable
its effect on alert visuals. Likewise Risk Status filters only alert visuals.
Avoid a common date slicer on this page: historical evaluation is in observed
December 2025, while alerts target the following week. Show
`[Alert Forecast Week]` and `[Inventory Snapshot Week]` as date cards so the time
context remains explicit. `linear_regression_prediction` can be added to an
evaluation-only tooltip; some historical values are negative, so label that
model output as an evaluation result rather than plausible demand.

## 11. Filters, interactions, and conditional formatting

| Page | Visible slicers | Special interaction |
|---|---|---|
| Executive Overview | Date, Region, Category | Date has distinct sales-day and inventory-week meanings |
| Sales Performance | Date, Region, Product; optional Store/Category | Monthly Growth only on complete adjacent months |
| Inventory Health | Region, Store, Category, Risk Status | Risk filters alert visuals only |
| Supplier Performance | Supplier, Category | Static supplier attributes remain static |
| Forecast & Alerts | Store, Product, Risk Status | Risk filters alerts; optional historical date filters evaluation only |

For risk tables, use **Conditional formatting → Background color or Icons**
with `STOCKOUT_RISK` highest attention, `LOW_STOCK` elevated attention,
`OVERSTOCK` excess-stock attention, and `NORMAL` neutral. Keep both
`risk_status` and `risk_reason` text visible so color is never the only signal.
Optional tooltips can show category, store, and the two alert dates; a
drill-through page is not required for Phase 5.

## 12. Validation checklist

1. With slicers cleared, `[Revenue]`, `[Orders]`, and `[Units Sold]` equal the
   current `data/processed/overall_kpi.csv` values. The Python generator
   already verifies this in integer cents and whole counts.
2. `FactSales[order_id]` and all three dimension keys are unique on their
   respective one side. FactInventory, FactForecastEvaluation, and FactAlerts
   retain their documented composite keys; no relationships connect facts.
3. `[Inventory Records]` and `[Stockout Records]` match the current
   `inventory_clean.csv`; the `[Stockout Rate]` and `[Fill Rate]` measures match
   Phase 2's weekly-record definitions.
4. `[Current Inventory]` agrees with the sum of `closing_stock` in
   `latest_inventory_snapshot.csv`. The Python generator checks equality by
   store/product, not just the total.
5. The four Risk Status counts sum to the row count of `inventory_alerts.csv`.
   Forecast evaluation rows remain unique by historical date/store/product.
6. `DimDate[Is Complete Month]` marks the same months as
   `monthly_kpi.csv[is_complete_month]`; MoM is blank for the first complete
   month, partial months, and a zero-revenue prior month.
7. Confirm the Page 3 and Page 5 slicer interactions visually. A risk filter
   must not change historical stockout or model-evaluation measures.

## 13. Limitations and synthetic-data disclaimer

All sales orders, transaction prices, revenue, and supplier master attributes
are **synthetic**. Each order has one item, so AOV is a synthetic single-item
proxy. Inventory accounting semantics for opening stock and receipts remain
unresolved, and some receipt values are missing. Stockout and fill rate are
weekly-record indicators, not order fulfillment. Inventory turnover is an
analytical proxy using synthetic cost. Phase 3's five-week holdout scores do
not establish real-world model accuracy. Phase 4's one-week forecast and risk
rules are prototypes, with no uncertainty interval or complete supplier
lead-time demand forecast. Supplier attributes and supplier-associated
stockouts do not establish delivery performance or causation. This is a
portfolio analytical prototype, not a production enterprise BI dashboard.
