# Retail Sales & Inventory Intelligence (SQL, Python, Power BI)

A reproducible **synthetic retail and supply-chain analytical prototype**. The extended pipeline cleans a weekly inventory ledger, generates clearly labeled single-item sales orders, validates them in SQLite, calculates business KPIs, evaluates demand forecasts, classifies inventory risk, and exports a Power BI-ready data layer. It is not a production enterprise system.

## Business Problem

The project provides one place to examine sales, inventory health, stockouts, estimated spoilage and lost sales, supplier-associated patterns, short-horizon demand forecasts, and rule-based inventory alerts. It helps demonstrate how these analytical steps fit together; synthetic associations and model scores do not establish real business outcomes or causes.

## Project Background and Original Project

This repository extends the public [Retail Inventory & Supply Chain Analytics project by DataWithSoumya](https://github.com/DataWithSoumya/retail-supply-chain-analytics). The original project's `analysis.py`, SQL, charts, recommendations, legacy flat Power BI dataset, and `retail-supply-chain-dashboard.pbix` remain in the repository. The separate `src/` pipeline and its Phase 1–6 outputs are the extension. The original work is not claimed as newly created here.

The original script explores weekly-record stockouts, approximate turnover, spoilage, supplier attributes, and a four-week moving-average example for one product. Its reported ~7% MAPE is an illustrative result, not a validated chain-wide forecast. The original charts remain under `images/`, including [stockouts by category](images/stockout_rate_by_category.png), [stockouts by region](images/stockout_rate_by_region.png), [turnover by category](images/inventory_turnover_by_category.png), [supplier lead time association](images/supplier_lead_time_vs_stockouts.png), [spoilage cost](images/spoilage_cost_by_category.png), and [the moving-average example](images/demand_forecast_vs_actual.png). See [the original recommendations](SUPPLY_CHAIN_RECOMMENDATIONS.md) for that analysis. Run `python analysis.py` separately if you want to regenerate its legacy outputs.

In that preserved analysis, the weekly-record fill-rate proxy is 98.2%, Packaged Foods has the highest category stockout rate at 2.2%, and Perishables has the largest estimated spoilage cost. The script reports correlations of -0.45 for supplier lead time and -0.44 for static reliability against supplier-associated stockout rates. These synthetic associations do not identify the cause of a stockout.

## Dataset

- The original synthetic weekly inventory ledger covers 52 weeks from 2025-01-06, 16 stores, 30 products, five product categories, and 10 suppliers. Store, product, and supplier master CSVs accompany it.
- `data/raw/` preserves those source CSVs. The Phase 1 cleaner creates `data/processed/inventory_clean.csv`, with 17,160 unique store/product/week rows from 17,417 source rows.
- `src.synthetic_sales` deterministically allocates each week's `units_sold` into synthetic single-item orders using seed 42. It writes `data/raw/sales.csv` and `data/processed/sales_clean.csv`; order dates, transaction prices, discounts, orders, and revenue are generated, not observed transactions.
- Supplier lead time and reliability are static synthetic master attributes. There is no purchase-order or delivery-history fact table.

## Architecture

```text
Original synthetic inventory + store/product/supplier CSVs
    -> data_cleaning -> inventory_clean.csv
    -> synthetic_sales -> sales_clean.csv
    -> database -> SQLite + SQL checks + data-quality report
    -> kpi_analysis -> KPI CSVs + latest inventory snapshot
    -> forecasting -> historical holdout predictions + evaluation report
    -> inventory_alerts -> next-week forecast and risk classifications
    -> powerbi_dataset -> order-grain sales CSV for a multi-fact BI model
```

`forecasting` reads the cleaned inventory and sales CSVs, while `inventory_alerts` reads those files plus the latest KPI snapshot. `powerbi_dataset` validates the separate sales, inventory, historical forecast, and future alert facts before exporting its sales fact. `main.py` calls the existing modules in this dependency order; it contains no business formulas.

## Data Cleaning

Phase 1 removes only exact duplicate inventory rows; conflicting rows with the same store/product/week key fail validation. Category text is trimmed and case-normalized against the product master's canonical categories. Dates must be valid Mondays, numeric fields must have valid types and ranges, and store/product/supplier references must match the master tables.

Missing `units_received` remains distinguishable through `units_received_raw`, `units_received_missing_flag`, and a nullable `units_received_clean`. The extended cleaner does **not** equate a missing receipt with zero. It reports inventory-balance and stockout-flag checks without rewriting the source ledger. The original `analysis.py` uses a different legacy cleaning choice and fills those missing values with zero. See [the generated data-quality report](reports/DATA_QUALITY_REPORT.md) for counts and unresolved receipt/accounting semantics.

## SQLite and SQL Analysis

`src.database` rebuilds `data/database/business_analytics.db` from the current cleaned facts and master data. Its schema enforces keys, references, nonnegative quantities, and receipt missingness. It runs all 18 queries in `sql/business_analysis.sql`, checks SQLite integrity, and reconciles row counts, sold units, order counts, and revenue in integer cents against pandas. The database is a rebuildable local artifact and is ignored by Git.

## KPI System

`src.kpi_analysis` keeps sales orders and weekly inventory as separate facts, so joining order rows cannot multiply inventory measures. It produces overall, monthly, product, category, region, store, and supplier KPIs plus a latest-inventory snapshot. [The generated KPI dictionary](reports/KPI_DICTIONARY.md) is the full definition source.

| KPI | Current definition and interpretation |
|---|---|
| Synthetic Revenue, Orders, Units Sold | Sum generated `sales.revenue`, count unique single-item `order_id`, and sum `sales.quantity`; units reconcile to inventory `units_sold`. |
| AOV and Average Selling Price | Revenue / Orders is a **synthetic single-item order proxy**, not basket AOV; Revenue / Units Sold is the average discounted selling price. |
| Revenue MoM Growth | Compares adjacent complete calendar months when prior revenue is positive; partial January 2025 and January 2026 are excluded. |
| Stockout Rate and Fill Rate | Mean weekly-inventory `stockout_flag`; Fill Rate = 1 − Stockout Rate. This is a **weekly-record proxy**, not order fulfillment. |
| Approx Inventory Turnover | Estimated units-sold cost divided by mean weekly closing-inventory value, using synthetic product costs; it is not an audited accounting ratio. |
| Supplier Reliability | A static synthetic master-data score, not measured delivery success. |

## Forecasting

`src.forecasting` aggregates generated orders back to the store/product/week inventory grain, explicitly includes verified zero-sales weeks, and compares a previous-week **Naive Baseline**, **Linear Regression**, and **Random Forest**. Features are `lag_1`, `lag_7`, shifted 7- and 30-week rolling means, month, and ISO week number. The lag and rolling values use only earlier observations from the same store/product series.

The train/test split is chronological and keeps whole weeks together. `data/processed/forecast_results.csv` contains **historical holdout** actuals and predictions, not a forecast for inventory after the last observed week. Random Forest uses a fixed seed. No test-week target or later observation enters the features for that same week.

## Model Evaluation

The generated [model evaluation report](reports/MODEL_EVALUATION.md) scores all three models on the same five held-out weeks, 2025-12-01 through 2025-12-29. MAE and RMSE are measured in units per store/product/week:

| Model | MAE | RMSE |
|---|---:|---:|
| Naive Baseline | 6.2752 | 8.7239 |
| Linear Regression | 8.8715 | 12.7098 |
| Random Forest | 5.3376 | 7.5017 |

The Random Forest is the provisional Phase 4 candidate because it beats the baseline on this synthetic holdout. These figures describe the current generated dataset and do not establish accuracy on real demand.

## Inventory Alerts

`src.inventory_alerts` trains the provisional Random Forest on all eligible observed history and builds a separate forecast for the week after the latest inventory snapshot. It combines that forecast with current stock, safety stock, reorder point, the last four observed weeks' average demand, and static supplier lead time. The historical `forecast_results.csv` is never joined to current stock as if it were a future forecast.

Risk status uses this priority:

1. `STOCKOUT_RISK`: current stock is at or below next-week forecast demand.
2. `LOW_STOCK`: otherwise, projected stock falls below safety stock or current stock is at or below reorder point.
3. `OVERSTOCK`: otherwise, current stock covers at least eight weeks of recent average demand, or positive stock has zero demand across the last four weeks.
4. `NORMAL`: none of those rules applies.

The eight-week threshold and all alerts are **rule-based prototype indicators**. They are not production replenishment decisions or a full supplier lead-time demand forecast.

## Power BI

`src.powerbi_dataset` exports `data/processed/powerbi_business_dataset.csv`, one synthetic single-item order per `order_id`. Its dimension enrichment uses unique store/product/supplier keys. It checks sales totals against Phase 2, inventory coverage, historical forecast keys, future alert keys, and latest-stock reconciliation. It does not join the separate facts onto each order and create a fan-out.

The [Power BI guide](powerbi/POWER_BI_GUIDE.md) describes a **Power BI-ready multi-fact semantic model**, DAX measures, and five pages: Executive Overview, Sales Performance, Inventory Health, Supplier Performance, and Forecast & Alerts. The five-page Phase 5 dashboard is a build guide, not a newly delivered PBIX. The tracked `retail-supply-chain-dashboard.pbix` belongs to the original project.

## Project Structure

```text
retail-supply-chain-analytics/
├── main.py                         # extended pipeline entry point
├── requirements.txt                # direct Python dependencies
├── README.md
├── analysis.py                      # preserved original workflow
├── retail-supply-chain-dashboard.pbix  # original PBIX
├── SUPPLY_CHAIN_RECOMMENDATIONS.md # original analysis recommendations
├── src/                            # seven Phase 1–5 modules
├── tests/                          # cleaning, sales, SQL, KPI, forecast, alert, BI, entry tests
├── data/
│   ├── raw/                        # preserved source + generated synthetic sales
│   ├── processed/                  # clean facts, KPIs, forecasts, alerts, BI sales fact
│   ├── database/                   # rebuildable SQLite database
│   └── *.csv                       # preserved original project data and outputs
├── sql/                            # current schema and 18 queries; legacy SQL files
├── reports/                        # generated quality, KPI, insight, model reports
├── powerbi/                         # five-page semantic-model and dashboard guide
├── images/                          # original and extended charts
└── docs/                            # introduction and historical project plans
```

## How to Run

Run from the repository root. The project was verified with Python 3.11.4; `requirements.txt` declares the five direct dependencies as compatible ranges rather than freezing an entire local environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

On macOS or Linux, activate with `source .venv/bin/activate` instead. An existing suitable Python environment can run the final three commands directly after installing the requirements. A stage prints `PASS` only after its module succeeds; an exception stops the pipeline with a nonzero exit.

Each module also runs independently, in this order:

```powershell
python -m src.data_cleaning
python -m src.synthetic_sales
python -m src.database
python -m src.kpi_analysis
python -m src.forecasting
python -m src.inventory_alerts
python -m src.powerbi_dataset
```

## Results

These figures are from the tracked Phase 1–5 outputs; rerunning `python main.py` regenerates and validates them. [Overall KPI CSV](data/processed/overall_kpi.csv), [forecast report](reports/MODEL_EVALUATION.md), [alert CSV](data/processed/inventory_alerts.csv), and [data-quality report](reports/DATA_QUALITY_REPORT.md) provide the underlying values.

| Measure | Current result | Meaning |
|---|---:|---|
| Clean inventory rows | 17,160 | 257 exact duplicates removed from the source ledger |
| Generated single-item orders | 149,949 | Synthetic, seed 42 |
| Units Sold | 705,399 | Generated sales reconcile to inventory |
| Synthetic Revenue | 336,627,819.99 | Generated discounted transaction prices |
| Weekly-record Stockout Rate | 1.77% | Based on inventory `stockout_flag` |
| Approx Inventory Turnover | 14.33 | Synthetic-cost analytical ratio |
| Phase 4 alerts | 330 | 30 stockout risk, 57 low stock, 56 overstock, 187 normal |

The Phase 5 order-grain export contains 149,949 rows. The model table above gives the current MAE/RMSE; its five test weeks and synthetic data limit interpretation.

## Limitations

- Sales orders, dates, transaction prices, discounts, revenue, and supplier attributes are synthetic. AOV is based on single-item orders.
- Inventory receipt/accounting semantics remain unresolved, and some `units_received` values are missing. A stockout flag is not always equivalent to zero closing stock.
- The forecast has only 52 observed inventory weeks, a 30-week feature history, five held-out test weeks, and a one-week future horizon. Observed sales during stockouts may understate unconstrained demand.
- Alerts use prototype thresholds without uncertainty bands or full lead-time demand. Supplier-associated stockouts do not prove supplier causation.
- The Power BI layer and guide are an analytical prototype; the old PBIX represents the original project, not the extended five-page model. No production deployment is provided.

## Data Disclaimer

All data and results are for portfolio and technical demonstration. They do not represent internal enterprise records, real orders, real company revenue, audited inventory performance, or operational forecasts.
