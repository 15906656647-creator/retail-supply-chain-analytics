"""One-week-ahead inventory risk indicators for synthetic retail data."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import forecasting
from .data_cleaning import PROCESSED, RAW, ROOT


SNAPSHOT_PATH = PROCESSED / "latest_inventory_snapshot.csv"
SUPPLIERS_PATH = RAW / "suppliers.csv"
ALERTS_PATH = PROCESSED / "inventory_alerts.csv"
SERIES_KEY = ["store_id", "product_id"]
OUTPUT_KEY = ["forecast_date", *SERIES_KEY]
AVERAGE_WEEKS = 4
OVERSTOCK_WEEKS = 8.0
RISK_STATUSES = ("NORMAL", "LOW_STOCK", "STOCKOUT_RISK", "OVERSTOCK")
OUTPUT_COLUMNS = [
    "forecast_date", "inventory_week_start", "store_id", "store_name", "region",
    "product_id", "product_name", "category", "supplier_id", "supplier_name",
    "supplier_lead_time_days", "current_stock", "forecast_demand",
    "safety_stock", "reorder_point", "average_weekly_demand",
    "projected_stock_after_forecast", "weeks_of_supply", "risk_status", "risk_reason",
]


def _nonnegative(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all() or (values < 0).any():
            raise ValueError(f"{column} must be finite and nonnegative")
        frame[column] = values


def load_alert_inputs(
    snapshot_path: Path = SNAPSHOT_PATH, suppliers_path: Path = SUPPLIERS_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the Phase 1 history, Phase 2 snapshot, and static supplier master."""
    sales, inventory = forecasting.load_forecasting_data()
    series = forecasting.build_time_series(sales, inventory)
    for path in (snapshot_path, suppliers_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    snapshot = pd.read_csv(snapshot_path, dtype={key: "string" for key in [*SERIES_KEY, "supplier_id"]})
    suppliers = pd.read_csv(suppliers_path, dtype={"supplier_id": "string"})
    required_snapshot = {
        *SERIES_KEY, "store_name", "region", "product_name", "category", "supplier_id",
        "week_start", "closing_stock", "reorder_point", "safety_stock",
    }
    required_suppliers = {"supplier_id", "supplier_name", "avg_lead_time_days"}
    if not required_snapshot.issubset(snapshot) or not required_suppliers.issubset(suppliers):
        raise ValueError("Snapshot or supplier master is missing required columns")
    if snapshot.empty or snapshot[SERIES_KEY].isna().any().any() or snapshot.duplicated(SERIES_KEY).any():
        raise ValueError("Latest inventory snapshot has missing or duplicate store/product keys")
    if suppliers.empty or suppliers["supplier_id"].isna().any() or suppliers["supplier_id"].duplicated().any():
        raise ValueError("Supplier master has missing or duplicate supplier_id")
    snapshot["week_start"] = pd.to_datetime(snapshot["week_start"], format="%Y-%m-%d", errors="raise")
    if snapshot["week_start"].isna().any() or snapshot["week_start"].nunique() != 1:
        raise ValueError("Latest inventory snapshot must contain exactly one inventory week")
    if snapshot["week_start"].iloc[0] != series["date"].max():
        raise ValueError("Latest inventory snapshot does not match the last observed demand week")
    if snapshot[["store_name", "region", "product_name", "category", "supplier_id"]].isna().any().any():
        raise ValueError("Latest inventory snapshot has missing descriptive fields")
    if suppliers[["supplier_name", "avg_lead_time_days"]].isna().any().any():
        raise ValueError("Supplier master has missing required values")
    _nonnegative(snapshot, ("closing_stock", "reorder_point", "safety_stock"))
    _nonnegative(suppliers, ("avg_lead_time_days",))
    return series, snapshot, suppliers


def calculate_average_demand(time_series: pd.DataFrame) -> pd.DataFrame:
    """Mean weekly units sold in the last four fully observed inventory weeks."""
    weeks = pd.DatetimeIndex(time_series["date"].unique()).sort_values()
    if len(weeks) < AVERAGE_WEEKS or not (weeks[-AVERAGE_WEEKS:].to_series().diff().dropna() == pd.Timedelta(days=7)).all():
        raise ValueError("Average demand requires four consecutive observed weeks")
    recent = time_series.loc[time_series["date"].isin(weeks[-AVERAGE_WEEKS:])]
    grouped = recent.groupby(SERIES_KEY, as_index=False)["units_sold"].agg(["mean", "count"])
    if grouped.empty or not grouped["count"].eq(AVERAGE_WEEKS).all():
        raise ValueError("Every store/product needs four observed demand weeks")
    result = grouped.rename(columns={"mean": "average_weekly_demand"})
    return result[[*SERIES_KEY, "average_weekly_demand"]]


def prepare_alert_dataset(
    forecast: pd.DataFrame, snapshot: pd.DataFrame, suppliers: pd.DataFrame,
    average_demand: pd.DataFrame,
) -> pd.DataFrame:
    """Join at checked grains and reject missing or multiplied rows."""
    if forecast.empty or forecast.duplicated(OUTPUT_KEY).any() or forecast[SERIES_KEY].isna().any().any():
        raise ValueError("Next-week forecast has missing or duplicate keys")
    if forecast["forecast_date"].nunique() != 1 or snapshot["week_start"].nunique() != 1:
        raise ValueError("Forecast and snapshot must each describe one week")
    if forecast["forecast_date"].iloc[0] != snapshot["week_start"].iloc[0] + pd.Timedelta(days=7):
        raise ValueError("Forecast date must be the week after the inventory snapshot")
    forecast_pairs = set(map(tuple, forecast[SERIES_KEY].itertuples(index=False, name=None)))
    snapshot_pairs = set(map(tuple, snapshot[SERIES_KEY].itertuples(index=False, name=None)))
    if forecast_pairs != snapshot_pairs or len(forecast) != len(snapshot):
        raise ValueError("Forecast and inventory store/product coverage differ")
    if average_demand.duplicated(SERIES_KEY).any() or len(average_demand) != len(forecast):
        raise ValueError("Average demand coverage or key uniqueness failed")
    joined = forecast.merge(snapshot, on=SERIES_KEY, how="inner", validate="one_to_one")
    joined = joined.merge(average_demand, on=SERIES_KEY, how="left", validate="one_to_one")
    joined = joined.merge(
        suppliers[["supplier_id", "supplier_name", "avg_lead_time_days"]],
        on="supplier_id", how="left", validate="many_to_one",
    )
    if len(joined) != len(forecast) or joined[["average_weekly_demand", "supplier_name", "avg_lead_time_days"]].isna().any().any():
        raise ValueError("Alert input join lost or multiplied rows")
    return joined.rename(columns={
        "week_start": "inventory_week_start", "closing_stock": "current_stock",
        "avg_lead_time_days": "supplier_lead_time_days",
    })


def classify_risk(
    current_stock: float, forecast_demand: float, safety_stock: float,
    reorder_point: float, average_weekly_demand: float,
    *, overstock_weeks: float = OVERSTOCK_WEEKS,
) -> tuple[str, str]:
    """Classify one row with explicit stockout > low > overstock > normal priority."""
    numbers = (current_stock, forecast_demand, safety_stock, reorder_point, average_weekly_demand)
    if not all(np.isfinite(value) and value >= 0 for value in numbers):
        raise ValueError("Inventory risk inputs must be finite and nonnegative")
    if not np.isfinite(overstock_weeks) or overstock_weeks <= 0:
        raise ValueError("Overstock threshold must be positive")
    if current_stock <= forecast_demand:
        reason = "Current stock is zero" if current_stock == 0 else "Forecast demand meets or exceeds current stock"
        return "STOCKOUT_RISK", reason
    projected = current_stock - forecast_demand
    low_reasons = []
    if projected < safety_stock:
        low_reasons.append("Projected stock after next-week demand falls below safety stock")
    if current_stock <= reorder_point:
        low_reasons.append("Current stock is at or below reorder point")
    if low_reasons:
        return "LOW_STOCK", "; ".join(low_reasons)
    if average_weekly_demand == 0 and current_stock > 0:
        return "OVERSTOCK", "Positive stock remains despite zero demand in the last four observed weeks"
    if average_weekly_demand > 0 and current_stock / average_weekly_demand >= overstock_weeks:
        return "OVERSTOCK", f"Inventory covers at least {overstock_weeks:g} weeks of recent average demand"
    return "NORMAL", "Stock exceeds next-week forecast and reorder point; projected stock meets safety stock; supply is below the overstock threshold"


def calculate_inventory_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    _nonnegative(result, ("current_stock", "forecast_demand", "safety_stock", "reorder_point", "average_weekly_demand", "supplier_lead_time_days"))
    result["projected_stock_after_forecast"] = result["current_stock"] - result["forecast_demand"]
    result["weeks_of_supply"] = result["current_stock"].div(result["average_weekly_demand"].replace(0, np.nan))
    classifications = result.apply(
        lambda row: classify_risk(
            row["current_stock"], row["forecast_demand"], row["safety_stock"],
            row["reorder_point"], row["average_weekly_demand"],
        ), axis=1,
    )
    result[["risk_status", "risk_reason"]] = pd.DataFrame(classifications.tolist(), index=result.index)
    return result[OUTPUT_COLUMNS].sort_values(OUTPUT_KEY).reset_index(drop=True)


def validate_alerts(alerts: pd.DataFrame) -> dict[str, object]:
    if alerts.empty or alerts.duplicated(OUTPUT_KEY).any() or alerts[OUTPUT_KEY].isna().any().any():
        raise ValueError("Alert output must have unique, nonmissing forecast/store/product keys")
    required = [column for column in OUTPUT_COLUMNS if column != "weeks_of_supply"]
    if alerts[required].isna().any().any():
        raise ValueError("Alert output has missing required values")
    if not alerts["forecast_date"].gt(alerts["inventory_week_start"]).all():
        raise ValueError("Alert forecast date must follow the inventory snapshot")
    _nonnegative(alerts, ("current_stock", "forecast_demand", "safety_stock", "reorder_point", "average_weekly_demand"))
    if not alerts["risk_status"].isin(RISK_STATUSES).all() or alerts["risk_reason"].astype(str).str.strip().eq("").any():
        raise ValueError("Alert status or explanation is invalid")
    if alerts.loc[alerts["average_weekly_demand"].eq(0), "weeks_of_supply"].notna().any():
        raise ValueError("Weeks of supply must be empty when average demand is zero")
    counts = {status: int(alerts["risk_status"].eq(status).sum()) for status in RISK_STATUSES}
    if max(counts.values()) == len(alerts):
        raise ValueError("All alerts have one status; inspect joins and risk rules")
    percentages = {status: round(count / len(alerts) * 100, 2) for status, count in counts.items()}
    return {
        "unique_store_product_pairs": len(alerts[SERIES_KEY].drop_duplicates()),
        "risk_counts": counts,
        "risk_percentages": percentages,
        "distribution_warning": any(share >= 90 for share in percentages.values()),
        "key_uniqueness": "PASS",
        "nonnegative_inputs": "PASS",
        "risk_reasons": "PASS",
    }


def export_alerts(alerts: pd.DataFrame, output_path: Path = ALERTS_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    alerts.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(output_path)


def run() -> dict[str, object]:
    series, snapshot, suppliers = load_alert_inputs()
    training_rows = len(forecasting.create_features(series).dropna(subset=forecasting.FEATURES))
    future = forecasting.forecast_next_week(series)
    average = calculate_average_demand(series)
    joined = prepare_alert_dataset(future, snapshot, suppliers, average)
    alerts = calculate_inventory_metrics(joined)
    checks = validate_alerts(alerts)
    export_alerts(alerts)
    return {
        "status": "PASS",
        "model": "RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)",
        "latest_observed_week": series["date"].max().strftime("%Y-%m-%d"),
        "snapshot_date": snapshot["week_start"].iloc[0].strftime("%Y-%m-%d"),
        "forecast_date": future["forecast_date"].iloc[0].strftime("%Y-%m-%d"),
        "training_rows": training_rows,
        "snapshot_rows": len(snapshot),
        "rows": len(alerts),
        "average_window_weeks": AVERAGE_WEEKS,
        "overstock_threshold_weeks": OVERSTOCK_WEEKS,
        **checks,
        "validation_status": "PASS",
        "output_path": str(ALERTS_PATH.relative_to(ROOT)),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
