# Model Evaluation — Phase 3

## 1. Objective

Evaluate whether simple one-week-ahead models predict synthetic units sold better than a previous-week naive baseline.

## 2. Dataset

Synthetic single-item sales orders are aggregated to weekly quantity and reconciled to the cleaned weekly inventory ledger. There are 330 store/product series, 17,160 weekly observations, 10 verified zero-sales weeks, and 7,260 observations after the 30-week history window.

## 3. Forecasting Grain

One row per inventory week start × store_id × product_id. Daily order dates were randomly allocated inside their source inventory week; weekly modeling follows the original demand grain. lag_7 is seven weeks ago; rolling_mean_30 averages the preceding 30 weeks.

## 4. Date Range

Synthetic order dates: 2025-01-06 to 2026-01-04. Inventory weeks: 2025-01-06 to 2025-12-29; each week covers seven days. Eligible modeling weeks: 2025-08-04 to 2025-12-29.

## 5. Target Variable

units_sold, measured in units per store/product/week; derived from SUM(sales.quantity) and checked against inventory.units_sold. Revenue is not a target or model feature.

## 6. Feature Engineering

lag_1, lag_7, rolling_mean_7, rolling_mean_30, month, and ISO week_of_year. Store and product identifiers define independent history and identify output rows; they are not model features. Rows without the full 30 prior weeks are removed after all features are built.

## 7. Leakage Prevention

Every lag is grouped by store/product. Both rolling means use shift(1) before rolling, excluding the target week. Models fit only on training weeks. The test is a rolling one-week-ahead evaluation: an earlier test week's actual demand becomes available before forecasting the next test week; no current or later week's actual enters its features.

## 8. Train / Test Split

Training: 2025-08-04 to 2025-11-24, 5,610 rows across 17 weeks. Testing: 2025-12-01 to 2025-12-29, 1,650 rows across 5 weeks. Date split ratio: 17/22 training weeks (77.27%); all rows from a week stay in one split.

## 9. Models

Naive Baseline = lag_1; LinearRegression with defaults; RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1). The two learned models share one panel training set and the same six numeric features.

## 10. Evaluation Metrics

MAE and RMSE are calculated in units sold per store/product/week on the same test rows for all three models. Predictions are scored as produced, without clipping or tuning on the test set.

## 11. Model Results

| Model | MAE | RMSE |
|---|---:|---:|
| Naive Baseline | 6.2752 | 8.7239 |
| Linear Regression | 8.8715 | 12.7098 |
| Random Forest | 5.3376 | 7.5017 |

## 12. Baseline Comparison

- Linear Regression versus naive: MAE -41.37%; RMSE -45.69%. Improves both: no.
- Random Forest versus naive: MAE +14.94%; RMSE +14.01%. Improves both: yes.

Lowest MAE: Random Forest; lowest RMSE: Random Forest. Percentage differences are error reductions relative to naive, observed on only 5 held-out weeks; a negative value means the model is worse. They are not evidence of statistical significance.

Descriptive 'noticeable improvement' rule: at least 10% lower MAE and RMSE than naive. Models meeting it: Random Forest. This threshold is not a statistical test.

## 13. Forecast Interpretation

`forecast_results.csv` contains retrospective test-week actuals and predictions, not a forecast beyond the observed history. Negative predictions (physically implausible weekly demand): Linear Regression: 73, Random Forest: 0. The lowest measured error is an evaluation result, not proof of operational usefulness.

## 14. Model Limitations

The 30-week rolling feature leaves 17 training weeks and 5 test weeks. Models use no promotions, holidays, price changes, or stock availability. Observed sales may understate unconstrained demand during stockouts. No hyperparameter search or uncertainty interval is included.

## 15. Synthetic Data Limitations

Sales data is synthetic: orders are not real transactions, order dates are generated within inventory weeks, and every order contains one product. Demand patterns partly reflect the generation mechanism. Measured performance cannot represent accuracy on real enterprise data. This phase validates a technical workflow, not a production model deployment.

## 16. Recommendation for Phase 4

For a Phase 4 prototype, use Random Forest as the provisional candidate based on this holdout. A learned model is recommended only if it beats naive on both MAE and RMSE and has no negative test predictions. Rebuild a genuine next-week forecast from history before comparing demand with current stock; do not join these historical test predictions directly to the latest inventory snapshot. Validate on real sales and more time periods before any operational use.
