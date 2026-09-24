"""Build a Power BI sales fact without joining facts of different grains.

The exported business dataset has exactly one row per synthetic order_id.
Inventory, historical forecast evaluation, and future alerts remain separate
facts in the Power BI semantic model; they are read here for reconciliation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .data_cleaning import ROOT


OUTPUT_PATH = ROOT / "data" / "processed" / "powerbi_business_dataset.csv"
SALES_KEY = ["order_id"]
INVENTORY_KEY = ["week_start", "store_id", "product_id"]
PAIR_KEY = ["store_id", "product_id"]
FORECAST_KEY = ["date", *PAIR_KEY]
ALERT_KEY = ["forecast_date", *PAIR_KEY]
RISK_STATUSES = {"NORMAL", "LOW_STOCK", "STOCKOUT_RISK", "OVERSTOCK"}
OUTPUT_COLUMNS = [
    "order_id", "order_date", "week_start", "store_id", "store_name",
    "region", "store_type", "product_id", "product_name", "category",
    "supplier_id", "supplier_name", "avg_lead_time_days", "reliability_score",
    "quantity", "catalog_unit_price", "transaction_unit_price", "revenue",
    "synthetic_flag",
]


def _require(frame: pd.DataFrame, name: str, columns: list[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing or frame.empty:
        raise ValueError(f"{name}: empty input or missing columns {missing}")


def _key(frame: pd.DataFrame, name: str, columns: list[str]) -> None:
    _require(frame, name, columns)
    if (frame[columns].isna().any().any()
            or frame[columns].astype(str).apply(lambda field: field.str.strip().eq("")).any().any()):
        raise ValueError(f"{name}: missing key values in {columns}")
    if frame.duplicated(columns).any():
        raise ValueError(f"{name}: duplicate key {columns}")


def _numbers(
    frame: pd.DataFrame, name: str, columns: list[str], *,
    positive: tuple[str, ...] = (), integral: tuple[str, ...] = (),
    nullable: tuple[str, ...] = (),
) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise")
        if column not in nullable and values.isna().any():
            raise ValueError(f"{name}.{column}: missing numeric value")
        nonnull = values.dropna().to_numpy(dtype=float)
        if not np.isfinite(nonnull).all() or (nonnull < 0).any():
            raise ValueError(f"{name}.{column}: nonfinite or negative value")
        if column in positive and (nonnull <= 0).any():
            raise ValueError(f"{name}.{column}: expected positive value")
        if column in integral and (nonnull % 1 != 0).any():
            raise ValueError(f"{name}.{column}: expected integer value")


def _dates(frame: pd.DataFrame, name: str, column: str) -> pd.Series:
    _require(frame, name, [column])
    parsed = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{name}.{column}: missing or invalid date")
    return parsed


def _cents(values: pd.Series, name: str) -> np.ndarray:
    numeric = pd.to_numeric(values, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError(f"{name}: expected finite two-decimal currency values")
    cents = np.rint(numeric * 100).astype(np.int64)
    if not np.allclose(numeric * 100, cents, rtol=0, atol=1e-6):
        raise ValueError(f"{name}: expected finite two-decimal currency values")
    return cents


def load_powerbi_inputs(root: Path = ROOT) -> dict[str, pd.DataFrame]:
    """Read the already validated Phase 1–4 files; never regenerate them."""
    files = {
        "sales": "data/processed/sales_clean.csv",
        "inventory": "data/processed/inventory_clean.csv",
        "snapshot": "data/processed/latest_inventory_snapshot.csv",
        "forecast": "data/processed/forecast_results.csv",
        "alerts": "data/processed/inventory_alerts.csv",
        "overall": "data/processed/overall_kpi.csv",
        "stores": "data/raw/stores.csv",
        "products": "data/raw/products.csv",
        "suppliers": "data/raw/suppliers.csv",
    }
    data = {}
    for name, relative in files.items():
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        data[name] = pd.read_csv(path, dtype={
            key: "string" for key in ("order_id", "store_id", "product_id", "supplier_id")
        })
    return data


def validate_dimensions(data: dict[str, pd.DataFrame]) -> None:
    stores, products, suppliers = (data[name] for name in ("stores", "products", "suppliers"))
    for name, frame, key, fields in (
        ("stores", stores, "store_id", ["store_name", "region", "store_type"]),
        ("products", products, "product_id", ["product_name", "category", "supplier_id", "unit_cost", "unit_price"]),
        ("suppliers", suppliers, "supplier_id", ["supplier_name", "avg_lead_time_days", "reliability_score"]),
    ):
        _key(frame, name, [key])
        _require(frame, name, fields)
        if frame[[field for field in fields if field not in ("unit_cost", "unit_price", "avg_lead_time_days", "reliability_score")]].isna().any().any():
            raise ValueError(f"{name}: missing descriptive attribute")
    _numbers(products, "products", ["unit_cost", "unit_price"], positive=("unit_price",))
    _numbers(suppliers, "suppliers", ["avg_lead_time_days", "reliability_score"])
    if (pd.to_numeric(suppliers["reliability_score"]) > 1).any():
        raise ValueError("suppliers.reliability_score must not exceed 1")
    if not products["supplier_id"].isin(suppliers["supplier_id"]).all():
        raise ValueError("products: unknown supplier_id")


def prepare_sales_fact(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Attach only functional dimensions to order rows with checked joins."""
    validate_dimensions(data)
    sales = data["sales"]
    _key(sales, "sales", SALES_KEY)
    _require(sales, "sales", [
        "order_date", "week_start", "store_id", "product_id", "quantity",
        "catalog_unit_price", "transaction_unit_price", "revenue", "synthetic_flag",
    ])
    _numbers(sales, "sales", ["quantity", "catalog_unit_price", "transaction_unit_price", "revenue", "synthetic_flag"],
             positive=("quantity", "catalog_unit_price", "transaction_unit_price", "revenue"),
             integral=("quantity", "synthetic_flag"))
    if not pd.to_numeric(sales["synthetic_flag"]).eq(1).all():
        raise ValueError("sales: synthetic_flag must be 1")
    order_dates = _dates(sales, "sales", "order_date")
    weeks = _dates(sales, "sales", "week_start")
    if not (order_dates - weeks).dt.days.between(0, 6).all() or not weeks.dt.weekday.eq(0).all():
        raise ValueError("sales: order_date must fall inside its Monday inventory week")
    if not np.array_equal(
        _cents(sales["revenue"], "sales.revenue"),
        _cents(sales["transaction_unit_price"], "sales.transaction_unit_price")
        * pd.to_numeric(sales["quantity"]).to_numpy(dtype=np.int64),
    ):
        raise ValueError("sales: revenue differs from quantity times transaction price")
    result = sales.merge(
        data["stores"][["store_id", "store_name", "region", "store_type"]],
        on="store_id", how="left", validate="many_to_one",
    ).merge(
        data["products"][["product_id", "product_name", "category", "supplier_id"]],
        on="product_id", how="left", validate="many_to_one",
    ).merge(
        data["suppliers"][["supplier_id", "supplier_name", "avg_lead_time_days", "reliability_score"]],
        on="supplier_id", how="left", validate="many_to_one",
    )
    if len(result) != len(sales) or result[OUTPUT_COLUMNS].isna().any().any():
        raise ValueError("sales: dimension join lost, multiplied, or failed to map orders")
    return result[OUTPUT_COLUMNS].sort_values("order_id").reset_index(drop=True)


def _same_pairs(left: pd.DataFrame, right: pd.DataFrame, name: str) -> None:
    a = set(map(tuple, left[PAIR_KEY].itertuples(index=False, name=None)))
    b = set(map(tuple, right[PAIR_KEY].itertuples(index=False, name=None)))
    if a != b:
        raise ValueError(f"{name}: store/product coverage differs")


def validate_powerbi_dataset(dataset: pd.DataFrame, data: dict[str, pd.DataFrame]) -> dict[str, object]:
    """Reconcile all four independent facts before exporting the sales fact."""
    sales, inventory, snapshot, forecast, alerts, overall = (
        data[name] for name in ("sales", "inventory", "snapshot", "forecast", "alerts", "overall")
    )
    _key(dataset, "powerbi_business_dataset", SALES_KEY)
    if list(dataset.columns) != OUTPUT_COLUMNS or len(dataset) != len(sales):
        raise ValueError("powerbi_business_dataset: schema or sales row count differs")
    source = sales.set_index("order_id").sort_index()
    output = dataset.set_index("order_id").sort_index()
    if not output.index.equals(source.index) or not output[["quantity", "revenue"]].equals(source[["quantity", "revenue"]]):
        raise ValueError("powerbi_business_dataset: order measures changed")
    _key(overall, "overall_kpi", ["metric"])
    expected = overall.set_index("metric")["value"]
    for metric in ("Synthetic Revenue", "Synthetic Orders", "Units Sold", "Stockout Rate"):
        if metric not in expected:
            raise ValueError(f"overall_kpi: missing {metric}")
    revenue_cents = int(_cents(dataset["revenue"], "dataset.revenue").sum())
    orders = int(dataset["order_id"].nunique())
    units = int(pd.to_numeric(dataset["quantity"]).sum())
    if (revenue_cents != int(_cents(pd.Series([expected["Synthetic Revenue"]]), "overall revenue")[0])
            or orders != float(expected["Synthetic Orders"])
            or units != float(expected["Units Sold"])):
        raise ValueError("Sales reconciliation failed against Phase 2 overall KPI")

    _key(inventory, "inventory", INVENTORY_KEY)
    _require(inventory, "inventory", [
        "category", "supplier_id", "opening_stock", "units_received_missing_flag",
        "units_received_clean", "units_sold", "closing_stock", "stockout_flag",
        "reorder_point", "safety_stock",
    ])
    _numbers(inventory, "inventory", [
        "opening_stock", "units_received_missing_flag", "units_received_clean",
        "units_sold", "closing_stock", "stockout_flag", "reorder_point", "safety_stock",
    ], integral=("opening_stock", "units_received_missing_flag", "units_received_clean", "units_sold",
                 "closing_stock", "stockout_flag", "reorder_point", "safety_stock"),
        nullable=("units_received_clean",))
    if not pd.to_numeric(inventory["stockout_flag"]).isin([0, 1]).all():
        raise ValueError("inventory: stockout_flag must be 0 or 1")
    weeks = _dates(inventory, "inventory", "week_start")
    distinct_weeks = weeks.drop_duplicates().sort_values()
    if not weeks.dt.weekday.eq(0).all() or not distinct_weeks.diff().dropna().eq(pd.Timedelta(days=7)).all():
        raise ValueError("inventory: expected contiguous Monday weeks")
    products = data["products"].set_index("product_id")
    if (not inventory["product_id"].isin(products.index).all()
            or not inventory["store_id"].isin(data["stores"]["store_id"]).all()
            or not inventory["supplier_id"].equals(inventory["product_id"].map(products["supplier_id"]))
            or not inventory["category"].equals(inventory["product_id"].map(products["category"]))):
        raise ValueError("inventory: dimension relationship mismatch")
    stockout_count = int(pd.to_numeric(inventory["stockout_flag"]).sum())
    if not math.isclose(stockout_count / len(inventory), float(expected["Stockout Rate"]), abs_tol=1e-8):
        raise ValueError("inventory: stockout rate differs from Phase 2 overall KPI")
    if int(pd.to_numeric(inventory["units_sold"]).sum()) != units:
        raise ValueError("inventory: units sold differ from sales")
    inventory_units = inventory.set_index(INVENTORY_KEY)["units_sold"].astype("int64")
    sales_units = dataset.groupby(INVENTORY_KEY)["quantity"].sum()
    if (not sales_units.index.isin(inventory_units.index).all()
            or not sales_units.reindex(inventory_units.index, fill_value=0).eq(inventory_units).all()):
        raise ValueError("inventory: weekly store/product units differ from sales")

    _key(snapshot, "latest_inventory_snapshot", PAIR_KEY)
    _require(snapshot, "latest_inventory_snapshot", [
        "week_start", "closing_stock", "stockout_flag", "supplier_id", "category", "safety_stock", "reorder_point",
        "inventory_value",
    ])
    _numbers(snapshot, "latest_inventory_snapshot", [
        "closing_stock", "stockout_flag", "safety_stock", "reorder_point", "inventory_value",
    ], integral=("closing_stock", "stockout_flag", "safety_stock", "reorder_point"))
    snapshot_dates = _dates(snapshot, "snapshot", "week_start")
    if snapshot_dates.nunique() != 1 or snapshot_dates.iloc[0] != weeks.max():
        raise ValueError("snapshot: date is not the latest inventory week")
    latest = inventory.loc[weeks.eq(weeks.max())]
    _same_pairs(snapshot, latest, "snapshot")
    checked_snapshot = snapshot.merge(
        latest[PAIR_KEY + ["closing_stock", "stockout_flag", "supplier_id", "category", "safety_stock", "reorder_point"]],
        on=PAIR_KEY, suffixes=("_snapshot", "_inventory"), validate="one_to_one",
    )
    for field in ("closing_stock", "stockout_flag", "supplier_id", "category", "safety_stock", "reorder_point"):
        if not checked_snapshot[f"{field}_snapshot"].equals(checked_snapshot[f"{field}_inventory"]):
            raise ValueError(f"snapshot: {field} differs from latest inventory")
    product_cost_cents = pd.Series(
        _cents(products["unit_cost"], "products.unit_cost"), index=products.index,
    )
    expected_inventory_value = (
        pd.to_numeric(snapshot["closing_stock"]).to_numpy(dtype=np.int64)
        * snapshot["product_id"].map(product_cost_cents).to_numpy(dtype=np.int64)
    )
    if not np.array_equal(
        _cents(snapshot["inventory_value"], "snapshot.inventory_value"), expected_inventory_value,
    ):
        raise ValueError("snapshot: inventory_value differs from closing stock times product cost")

    _key(forecast, "forecast_results", FORECAST_KEY)
    _require(forecast, "forecast_results", [
        "actual_demand", "naive_prediction", "linear_regression_prediction", "random_forest_prediction",
    ])
    _numbers(forecast, "forecast_results", ["actual_demand"], integral=("actual_demand",))
    for field in ("naive_prediction", "linear_regression_prediction", "random_forest_prediction"):
        values = pd.to_numeric(forecast[field], errors="raise")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"forecast_results.{field}: nonfinite prediction")
    _dates(forecast, "forecast_results", "date")
    evaluated = forecast.merge(
        inventory[INVENTORY_KEY + ["units_sold"]],
        left_on=FORECAST_KEY, right_on=INVENTORY_KEY,
        how="left", validate="one_to_one", indicator=True,
    )
    if not evaluated["_merge"].eq("both").all() or not evaluated["actual_demand"].eq(evaluated["units_sold"]).all():
        raise ValueError("forecast_results: historical actuals do not match inventory")

    _key(alerts, "inventory_alerts", ALERT_KEY)
    _require(alerts, "inventory_alerts", [
        "inventory_week_start", "current_stock", "forecast_demand", "risk_status", "risk_reason",
        "supplier_id", "safety_stock", "reorder_point", "average_weekly_demand",
    ])
    _numbers(alerts, "inventory_alerts", [
        "current_stock", "forecast_demand", "safety_stock", "reorder_point", "average_weekly_demand",
    ])
    alert_dates = _dates(alerts, "inventory_alerts", "forecast_date")
    alert_inventory_dates = _dates(alerts, "inventory_alerts", "inventory_week_start")
    if (alert_dates.nunique() != 1 or alert_inventory_dates.nunique() != 1
            or alert_inventory_dates.iloc[0] != snapshot_dates.iloc[0]
            or alert_dates.iloc[0] != snapshot_dates.iloc[0] + pd.Timedelta(days=7)):
        raise ValueError("inventory_alerts: forecast must be one week after the latest snapshot")
    if not alerts["risk_status"].isin(RISK_STATUSES).all() or alerts["risk_reason"].isna().any() or alerts["risk_reason"].astype(str).str.strip().eq("").any():
        raise ValueError("inventory_alerts: invalid risk status or reason")
    _same_pairs(alerts, snapshot, "inventory_alerts")
    checked_alerts = alerts.merge(
        snapshot[PAIR_KEY + ["closing_stock", "supplier_id", "safety_stock", "reorder_point"]],
        on=PAIR_KEY, suffixes=("_alert", "_snapshot"), validate="one_to_one",
    )
    for alert_field, snapshot_field in (
        ("current_stock", "closing_stock"), ("supplier_id_alert", "supplier_id_snapshot"),
        ("safety_stock_alert", "safety_stock_snapshot"), ("reorder_point_alert", "reorder_point_snapshot"),
    ):
        if not checked_alerts[alert_field].equals(checked_alerts[snapshot_field]):
            raise ValueError(f"inventory_alerts: {alert_field} differs from snapshot")
    risk_counts = {status: int(alerts["risk_status"].eq(status).sum()) for status in sorted(RISK_STATUSES)}
    if sum(risk_counts.values()) != len(alerts):
        raise ValueError("inventory_alerts: risk counts do not reconcile")

    return {
        "revenue": "PASS", "orders": "PASS", "units_sold": "PASS",
        "inventory": "PASS", "forecast_keys": "PASS", "alert_keys": "PASS",
        "revenue_cents": revenue_cents, "orders_count": orders, "units_count": units,
        "inventory_rows": len(inventory), "stockout_count": stockout_count,
        "forecast_rows": len(forecast), "alert_rows": len(alerts),
        "alert_forecast_date": alert_dates.iloc[0].strftime("%Y-%m-%d"),
        "risk_counts": risk_counts,
    }


def export_powerbi_dataset(dataset: pd.DataFrame, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    dataset.to_csv(temporary, index=False, date_format="%Y-%m-%d", lineterminator="\n")
    temporary.replace(path)


def run() -> dict[str, object]:
    data = load_powerbi_inputs()
    dataset = prepare_sales_fact(data)
    reconciliation = validate_powerbi_dataset(dataset, data)
    export_powerbi_dataset(dataset)
    return {
        "status": "PASS", "grain": "one synthetic single-item order_id per row",
        "primary_key": SALES_KEY, "rows": len(dataset), "columns": len(dataset.columns),
        "reconciliation": reconciliation,
        "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
