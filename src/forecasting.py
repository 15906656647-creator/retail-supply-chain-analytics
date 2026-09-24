"""Reproducible one-week-ahead demand evaluation on synthetic weekly sales."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .data_cleaning import PROCESSED, ROOT


SALES_PATH = PROCESSED / "sales_clean.csv"
INVENTORY_PATH = PROCESSED / "inventory_clean.csv"
RESULTS_PATH = PROCESSED / "forecast_results.csv"
REPORT_PATH = ROOT / "reports" / "MODEL_EVALUATION.md"
KEY = ["week_start", "store_id", "product_id"]
SERIES_KEY = ["store_id", "product_id"]
FEATURES = ["lag_1", "lag_7", "rolling_mean_7", "rolling_mean_30", "month", "week_of_year"]
RESULT_COLUMNS = [
    "date", "store_id", "product_id", "actual_demand", "naive_prediction",
    "linear_regression_prediction", "random_forest_prediction",
]


def _nonnegative_integer(series: pd.Series, name: str) -> pd.Series:
    values = pd.to_numeric(series, errors="raise")
    if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
        raise ValueError(f"{name} must contain nonnegative integers")
    return values.astype("int64")


def load_forecasting_data(
    sales_path: Path = SALES_PATH, inventory_path: Path = INVENTORY_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load only the columns needed for weekly demand and coverage checks."""
    for path, command in (
        (sales_path, "python -m src.synthetic_sales"),
        (inventory_path, "python -m src.data_cleaning"),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}; run {command} first")
    sales = pd.read_csv(
        sales_path, usecols=["order_date", *KEY, "quantity"],
        dtype={"store_id": "string", "product_id": "string"},
    )
    inventory = pd.read_csv(
        inventory_path, usecols=[*KEY, "units_sold"],
        dtype={"store_id": "string", "product_id": "string"},
    )
    for frame, columns in ((sales, ["order_date", "week_start"]), (inventory, ["week_start"])):
        for column in columns:
            frame[column] = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="raise")
    sales["quantity"] = _nonnegative_integer(sales["quantity"], "quantity")
    inventory["units_sold"] = _nonnegative_integer(inventory["units_sold"], "units_sold")
    return sales, inventory


def build_time_series(sales: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Aggregate orders and use inventory coverage to identify true zero weeks."""
    sales = sales.copy()
    inventory = inventory.copy()
    sales["week_start"] = pd.to_datetime(sales["week_start"])
    sales["order_date"] = pd.to_datetime(sales["order_date"])
    inventory["week_start"] = pd.to_datetime(inventory["week_start"])
    if inventory.empty or inventory[KEY].isna().any().any() or inventory.duplicated(KEY).any():
        raise ValueError("Inventory coverage is empty or has missing/duplicate keys")
    if sales[KEY + ["order_date"]].isna().any().any():
        raise ValueError("Sales contain missing dates or keys")
    if (inventory["week_start"].dt.dayofweek != 0).any():
        raise ValueError("Inventory week_start must be Monday")
    if not (sales["order_date"] - sales["week_start"]).dt.days.between(0, 6).all():
        raise ValueError("Sales order_date falls outside its inventory week")
    inventory["units_sold"] = _nonnegative_integer(inventory["units_sold"], "units_sold")
    sales["quantity"] = _nonnegative_integer(sales["quantity"], "quantity")

    weeks = pd.DatetimeIndex(inventory["week_start"].unique()).sort_values()
    expected_weeks = pd.date_range(weeks.min(), weeks.max(), freq="7D")
    if not weeks.equals(expected_weeks):
        raise ValueError("Inventory weeks are not continuous")
    pair_sizes = inventory.groupby(SERIES_KEY, dropna=False).size()
    if not pair_sizes.eq(len(weeks)).all():
        raise ValueError("A store/product series is missing an inventory week")

    weekly_sales = sales.groupby(KEY, as_index=False, sort=True)["quantity"].sum()
    unmatched = weekly_sales.merge(inventory[KEY], on=KEY, how="left", indicator=True)
    if unmatched["_merge"].ne("both").any():
        raise ValueError("Sales contain a store/product/week absent from inventory")
    series = inventory[KEY + ["units_sold"]].merge(
        weekly_sales, on=KEY, how="left", validate="one_to_one",
    )
    series["quantity"] = series["quantity"].fillna(0).astype("int64")
    if not series["quantity"].eq(series["units_sold"]).all():
        raise ValueError("Weekly synthetic sales do not reconcile to inventory units_sold")
    return (
        series.rename(columns={"week_start": "date"})
        .drop(columns="quantity")
        .sort_values(["date", *SERIES_KEY])
        .reset_index(drop=True)
    )


def create_features(time_series: pd.DataFrame) -> pd.DataFrame:
    """Build features using only previously observed weeks of each series."""
    frame = time_series.sort_values([*SERIES_KEY, "date"]).copy()
    if frame.duplicated(["date", *SERIES_KEY]).any():
        raise ValueError("Forecasting series has duplicate date/store/product keys")
    grouped = frame.groupby(SERIES_KEY, sort=False)["units_sold"]
    frame["lag_1"] = grouped.shift(1)
    frame["lag_7"] = grouped.shift(7)
    frame["rolling_mean_7"] = grouped.transform(
        lambda values: values.shift(1).rolling(7, min_periods=7).mean()
    )
    frame["rolling_mean_30"] = grouped.transform(
        lambda values: values.shift(1).rolling(30, min_periods=30).mean()
    )
    frame["month"] = frame["date"].dt.month
    frame["week_of_year"] = frame["date"].dt.isocalendar().week.astype("int64")
    return frame.sort_values(["date", *SERIES_KEY]).reset_index(drop=True)


def time_based_split(
    eligible: pd.DataFrame, train_fraction: float = 0.8,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split complete dates, never rows within a week."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    dates = pd.DatetimeIndex(eligible["date"].unique()).sort_values()
    cutoff_index = int(len(dates) * train_fraction)
    if cutoff_index < 1 or cutoff_index >= len(dates):
        raise ValueError("Not enough eligible weeks for a chronological split")
    cutoff = dates[cutoff_index]
    train = eligible.loc[eligible["date"] < cutoff].copy()
    test = eligible.loc[eligible["date"] >= cutoff].copy()
    if train.empty or test.empty or train["date"].max() >= test["date"].min():
        raise ValueError("Training and testing dates overlap")
    return train, test


def naive_forecast(test: pd.DataFrame) -> np.ndarray:
    return test["lag_1"].to_numpy(dtype=float)


def train_linear_regression(train: pd.DataFrame) -> LinearRegression:
    return LinearRegression().fit(train[FEATURES], train["units_sold"])


def train_random_forest(train: pd.DataFrame) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=100, random_state=42, n_jobs=-1,
    ).fit(train[FEATURES], train["units_sold"])


def evaluate_predictions(actual: pd.Series | np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    if (len(actual_values) == 0 or len(actual_values) != len(predicted_values)
            or not np.isfinite(actual_values).all() or not np.isfinite(predicted_values).all()):
        raise ValueError("Actual and predicted values must be finite, aligned, and nonempty")
    return {
        "mae": float(mean_absolute_error(actual_values, predicted_values)),
        "rmse": float(math.sqrt(mean_squared_error(actual_values, predicted_values))),
    }


def build_forecast_results(
    test: pd.DataFrame, predictions: dict[str, np.ndarray],
) -> pd.DataFrame:
    result = test[["date", *SERIES_KEY, "units_sold"]].rename(
        columns={"units_sold": "actual_demand"}
    ).copy()
    for name in ("naive", "linear_regression", "random_forest"):
        values = np.asarray(predictions[name], dtype=float)
        if len(values) != len(result) or not np.isfinite(values).all():
            raise ValueError(f"{name} predictions are missing or nonfinite")
        result[f"{name}_prediction"] = values
    if result["actual_demand"].isna().any() or result.duplicated(["date", *SERIES_KEY]).any():
        raise ValueError("Forecast results have missing actuals or duplicate keys")
    return result[RESULT_COLUMNS].sort_values(["date", *SERIES_KEY]).reset_index(drop=True)


def _date(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d")


def _change(base: float, value: float) -> str:
    if base == 0:
        return "n/a (zero baseline error)"
    return f"{(base - value) / base * 100:+.2f}%"


def write_model_report(
    sales: pd.DataFrame, series: pd.DataFrame, features: pd.DataFrame, train: pd.DataFrame,
    test: pd.DataFrame, results: pd.DataFrame,
    metrics: dict[str, dict[str, float]], report_path: Path = REPORT_PATH,
) -> str:
    """Render observed data and measured errors; no estimated result is hard-coded."""
    labels = {
        "naive": "Naive Baseline",
        "linear_regression": "Linear Regression",
        "random_forest": "Random Forest",
    }
    best_mae = min(metrics, key=lambda name: (metrics[name]["mae"], metrics[name]["rmse"]))
    best_rmse = min(metrics, key=lambda name: (metrics[name]["rmse"], metrics[name]["mae"]))
    baseline = metrics["naive"]
    qualifying = [name for name in ("linear_regression", "random_forest")
                  if metrics[name]["mae"] < baseline["mae"]
                  and metrics[name]["rmse"] < baseline["rmse"]
                  and not results[f"{name}_prediction"].lt(0).any()]
    recommended = min(qualifying, key=lambda name: (metrics[name]["mae"], metrics[name]["rmse"])) if qualifying else "naive"
    rows = [
        f"| {labels[name]} | {metrics[name]['mae']:.4f} | {metrics[name]['rmse']:.4f} |"
        for name in labels
    ]
    comparison = [
        f"- {labels[name]} versus naive: MAE {_change(baseline['mae'], metrics[name]['mae'])}; "
        f"RMSE {_change(baseline['rmse'], metrics[name]['rmse'])}. "
        f"Improves both: {'yes' if metrics[name]['mae'] < baseline['mae'] and metrics[name]['rmse'] < baseline['rmse'] else 'no'}."
        for name in ("linear_regression", "random_forest")
    ]
    noticeable = [name for name in ("linear_regression", "random_forest")
                  if baseline["mae"] > 0 and baseline["rmse"] > 0
                  and (baseline["mae"] - metrics[name]["mae"]) / baseline["mae"] >= 0.10
                  and (baseline["rmse"] - metrics[name]["rmse"]) / baseline["rmse"] >= 0.10]
    negatives = [
        f"{labels[name]}: {int(results[f'{name}_prediction'].lt(0).sum())}"
        for name in ("linear_regression", "random_forest")
    ]
    pair_count = series.groupby(SERIES_KEY).ngroups
    eligible_count = int(features[FEATURES].notna().all(axis=1).sum())
    lines = [
        "# Model Evaluation — Phase 3", "",
        "## 1. Objective", "",
        "Evaluate whether simple one-week-ahead models predict synthetic units sold better than a previous-week naive baseline.", "",
        "## 2. Dataset", "",
        f"Synthetic single-item sales orders are aggregated to weekly quantity and reconciled to the cleaned weekly inventory ledger. "
        f"There are {pair_count} store/product series, {len(series):,} weekly observations, {int(series['units_sold'].eq(0).sum())} verified zero-sales weeks, "
        f"and {eligible_count:,} observations after the 30-week history window.", "",
        "## 3. Forecasting Grain", "",
        "One row per inventory week start × store_id × product_id. Daily order dates were randomly allocated inside their source inventory week; weekly modeling follows the original demand grain. "
        "lag_7 is seven weeks ago; rolling_mean_30 averages the preceding 30 weeks.", "",
        "## 4. Date Range", "",
        f"Synthetic order dates: {_date(sales['order_date'].min())} to {_date(sales['order_date'].max())}. "
        f"Inventory weeks: {_date(series['date'].min())} to {_date(series['date'].max())}; each week covers seven days. "
        f"Eligible modeling weeks: {_date(features.loc[features[FEATURES].notna().all(axis=1), 'date'].min())} to {_date(features['date'].max())}.", "",
        "## 5. Target Variable", "",
        "units_sold, measured in units per store/product/week; derived from SUM(sales.quantity) and checked against inventory.units_sold. Revenue is not a target or model feature.", "",
        "## 6. Feature Engineering", "",
        "lag_1, lag_7, rolling_mean_7, rolling_mean_30, month, and ISO week_of_year. "
        "Store and product identifiers define independent history and identify output rows; they are not model features. "
        "Rows without the full 30 prior weeks are removed after all features are built.", "",
        "## 7. Leakage Prevention", "",
        "Every lag is grouped by store/product. Both rolling means use shift(1) before rolling, excluding the target week. "
        "Models fit only on training weeks. The test is a rolling one-week-ahead evaluation: an earlier test week's actual demand becomes available before forecasting the next test week; no current or later week's actual enters its features.", "",
        "## 8. Train / Test Split", "",
        f"Training: {_date(train['date'].min())} to {_date(train['date'].max())}, {len(train):,} rows across {train['date'].nunique()} weeks. "
        f"Testing: {_date(test['date'].min())} to {_date(test['date'].max())}, {len(test):,} rows across {test['date'].nunique()} weeks. "
        f"Date split ratio: {train['date'].nunique()}/{train['date'].nunique() + test['date'].nunique()} training weeks "
        f"({train['date'].nunique() / (train['date'].nunique() + test['date'].nunique()):.2%}); "
        "all rows from a week stay in one split.", "",
        "## 9. Models", "",
        "Naive Baseline = lag_1; LinearRegression with defaults; RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1). "
        "The two learned models share one panel training set and the same six numeric features.", "",
        "## 10. Evaluation Metrics", "",
        "MAE and RMSE are calculated in units sold per store/product/week on the same test rows for all three models. "
        "Predictions are scored as produced, without clipping or tuning on the test set.", "",
        "## 11. Model Results", "",
        "| Model | MAE | RMSE |", "|---|---:|---:|", *rows, "",
        "## 12. Baseline Comparison", "", *comparison, "",
        f"Lowest MAE: {labels[best_mae]}; lowest RMSE: {labels[best_rmse]}. "
        f"Percentage differences are error reductions relative to naive, observed on only {test['date'].nunique()} held-out weeks; "
        "a negative value means the model is worse. They are not evidence of statistical significance.", "",
        "Descriptive 'noticeable improvement' rule: at least 10% lower MAE and RMSE than naive. "
        f"Models meeting it: {', '.join(labels[name] for name in noticeable) if noticeable else 'none'}. "
        "This threshold is not a statistical test.", "",
        "## 13. Forecast Interpretation", "",
        "`forecast_results.csv` contains retrospective test-week actuals and predictions, not a forecast beyond the observed history. "
        f"Negative predictions (physically implausible weekly demand): {', '.join(negatives)}. "
        "The lowest measured error is an evaluation result, not proof of operational usefulness.", "",
        "## 14. Model Limitations", "",
        f"The 30-week rolling feature leaves {train['date'].nunique()} training weeks and {test['date'].nunique()} test weeks. "
        "Models use no promotions, holidays, price changes, or stock availability. "
        "Observed sales may understate unconstrained demand during stockouts. No hyperparameter search or uncertainty interval is included.", "",
        "## 15. Synthetic Data Limitations", "",
        "Sales data is synthetic: orders are not real transactions, order dates are generated within inventory weeks, and every order contains one product. "
        "Demand patterns partly reflect the generation mechanism. Measured performance cannot represent accuracy on real enterprise data. "
        "This phase validates a technical workflow, not a production model deployment.", "",
        "## 16. Recommendation for Phase 4", "",
        f"For a Phase 4 prototype, use {labels[recommended]} as the provisional candidate "
        "based on this holdout. A learned model is recommended only if it beats naive on both MAE and RMSE and has no negative test predictions. "
        "Rebuild a genuine next-week forecast from history before comparing demand with current stock; do not join these historical test predictions directly to the latest inventory snapshot. "
        "Validate on real sales and more time periods before any operational use.", "",
    ]
    report = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(report_path)
    return recommended


def run() -> dict[str, object]:
    sales, inventory = load_forecasting_data()
    series = build_time_series(sales, inventory)
    features = create_features(series)
    eligible = features.dropna(subset=FEATURES).copy()
    train, test = time_based_split(eligible)
    actual = test["units_sold"]

    # Establish the naive score before fitting either learned model.
    predictions = {"naive": naive_forecast(test)}
    metrics = {"naive": evaluate_predictions(actual, predictions["naive"])}
    linear = train_linear_regression(train)
    forest = train_random_forest(train)
    predictions["linear_regression"] = linear.predict(test[FEATURES])
    predictions["random_forest"] = forest.predict(test[FEATURES])
    for name in ("linear_regression", "random_forest"):
        metrics[name] = evaluate_predictions(actual, predictions[name])
    results = build_forecast_results(test, predictions)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RESULTS_PATH.with_suffix(".csv.tmp")
    results.to_csv(temporary, index=False, date_format="%Y-%m-%d", float_format="%.8f")
    temporary.replace(RESULTS_PATH)
    recommendation = write_model_report(sales, series, features, train, test, results, metrics)
    return {
        "grain": "week_start x store_id x product_id",
        "series": int(series.groupby(SERIES_KEY).ngroups),
        "observations": len(series),
        "zero_sales_weeks": int(series["units_sold"].eq(0).sum()),
        "eligible_rows": len(eligible),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_date_min": _date(train["date"].min()),
        "train_date_max": _date(train["date"].max()),
        "test_date_min": _date(test["date"].min()),
        "test_date_max": _date(test["date"].max()),
        "metrics": metrics,
        "phase4_prototype_candidate": recommendation,
        "results_path": str(RESULTS_PATH),
        "report_path": str(REPORT_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
