"""Reproducible Phase 2 synthetic business KPIs and dimensional analysis."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data_cleaning import ROOT


DATABASE = ROOT / "data" / "database" / "business_analytics.db"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
CHARTS = ROOT / "images" / "phase2"
MONEY_COLUMNS = {
    "synthetic_revenue", "synthetic_aov_proxy", "average_selling_price",
    "estimated_cogs", "estimated_lost_sales_value", "estimated_spoilage_cost",
    "latest_inventory_value", "inventory_value",
}
RATE_COLUMNS = {
    "stockout_rate", "record_based_fill_rate_proxy", "synthetic_revenue_share",
    "units_share", "mom_revenue_growth", "mom_units_growth",
}


def _cents(series: pd.Series) -> pd.Series:
    return np.rint(series.astype(float) * 100).astype("int64")


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else math.nan


def load_analysis_data(database: Path = DATABASE) -> dict[str, pd.DataFrame]:
    """Load independent SQLite facts; never join sales rows to inventory rows."""
    if not database.is_file():
        raise FileNotFoundError(
            f"Missing {database}. Run python -m src.data_cleaning, "
            "python -m src.synthetic_sales, then python -m src.database."
        )
    with sqlite3.connect(database) as connection:
        data = {table: pd.read_sql_query(f"SELECT * FROM {table}", connection)
                for table in ("sales", "inventory", "products", "stores", "suppliers")}
    sales, inventory = data["sales"], data["inventory"]
    if sales.empty or inventory.empty:
        raise ValueError("Sales and inventory must both contain data")
    if sales["order_id"].duplicated().any():
        raise ValueError("Expected one row per synthetic single-item order")
    if inventory.duplicated(["store_id", "product_id", "week_start"]).any():
        raise ValueError("Duplicate inventory store/product/week key")
    for table, key in (("products", "product_id"), ("stores", "store_id"),
                       ("suppliers", "supplier_id")):
        if data[table][key].duplicated().any():
            raise ValueError(f"Duplicate {table}.{key}")

    products = data["products"].copy()
    products["unit_cost_cents"] = _cents(products["unit_cost"])
    sales = sales.merge(products[["product_id", "product_name", "category", "supplier_id"]],
                        on="product_id", validate="many_to_one")
    sales = sales.merge(data["stores"], on="store_id", validate="many_to_one")
    inventory = inventory.drop(columns=["category", "supplier_id"]).merge(
        products[["product_id", "product_name", "category", "supplier_id",
                  "unit_cost_cents"]],
        on="product_id", validate="many_to_one"
    ).merge(data["stores"], on="store_id", validate="many_to_one")
    if len(sales) != len(data["sales"]) or len(inventory) != len(data["inventory"]):
        raise ValueError("Dimension join lost fact rows")
    sales["order_date"] = pd.to_datetime(sales["order_date"], format="%Y-%m-%d")
    inventory["week_start"] = pd.to_datetime(inventory["week_start"], format="%Y-%m-%d")
    sales["revenue_cents"] = _cents(sales["revenue"])
    sales["month"] = sales["order_date"].dt.strftime("%Y-%m")
    for name, quantity, price in (
        ("estimated_cogs_cents", "units_sold", "unit_cost_cents"),
        ("estimated_lost_sales_value_cents", "lost_sales_units", "unit_price_cents"),
        ("estimated_spoilage_cost_cents", "spoilage_units", "unit_cost_cents"),
        ("inventory_value_cents", "closing_stock", "unit_cost_cents"),
    ):
        if price == "unit_price_cents" and price not in inventory:
            inventory[price] = inventory["product_id"].map(
                products.set_index("product_id")["unit_price"].mul(100).round().astype("int64")
            )
        inventory[name] = inventory[quantity].astype("int64") * inventory[price]
    data["sales_fact"], data["inventory_fact"] = sales, inventory
    return data


def _sales_aggregate(sales: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return sales.groupby(keys, dropna=False, sort=True).agg(
        revenue_cents=("revenue_cents", "sum"),
        synthetic_orders=("order_id", "nunique"),
        units_sold=("quantity", "sum"),
    ).reset_index()


def _inventory_aggregate(inventory: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    grouped = inventory.groupby(keys, dropna=False, sort=True).agg(
        inventory_rows=("stockout_flag", "size"),
        stockout_rows=("stockout_flag", "sum"),
        lost_sales_units=("lost_sales_units", "sum"),
        estimated_lost_sales_value_cents=("estimated_lost_sales_value_cents", "sum"),
        spoilage_units=("spoilage_units", "sum"),
        estimated_spoilage_cost_cents=("estimated_spoilage_cost_cents", "sum"),
        estimated_cogs_cents=("estimated_cogs_cents", "sum"),
    ).reset_index()
    # First sum all store/product closing values within each week and group.
    weekly = inventory.groupby(keys + ["week_start"], sort=True)[
        "inventory_value_cents"
    ].sum().reset_index()
    averages = weekly.groupby(keys, sort=True)["inventory_value_cents"].mean(
    ).rename("average_inventory_value_cents").reset_index()
    return grouped.merge(averages, on=keys, validate="one_to_one")


def _dimension(data: dict[str, pd.DataFrame], keys: list[str],
               base: pd.DataFrame) -> pd.DataFrame:
    sales = _sales_aggregate(data["sales_fact"], keys)
    inventory = _inventory_aggregate(data["inventory_fact"], keys)
    result = base.merge(sales, on=keys, how="left", validate="one_to_one")
    result = result.merge(inventory, on=keys, how="left", validate="one_to_one")
    counts = ["revenue_cents", "synthetic_orders", "units_sold", "inventory_rows",
              "stockout_rows", "lost_sales_units", "estimated_lost_sales_value_cents",
              "spoilage_units", "estimated_spoilage_cost_cents", "estimated_cogs_cents"]
    result[counts] = result[counts].fillna(0).astype("int64")
    result["synthetic_revenue"] = result["revenue_cents"] / 100
    result["synthetic_aov_proxy"] = result.apply(
        lambda row: _ratio(row.revenue_cents, row.synthetic_orders * 100), axis=1)
    result["average_selling_price"] = result.apply(
        lambda row: _ratio(row.revenue_cents, row.units_sold * 100), axis=1)
    result["stockout_rate"] = result.apply(
        lambda row: _ratio(row.stockout_rows, row.inventory_rows), axis=1)
    result["estimated_lost_sales_value"] = result["estimated_lost_sales_value_cents"] / 100
    result["estimated_spoilage_cost"] = result["estimated_spoilage_cost_cents"] / 100
    result["estimated_cogs"] = result["estimated_cogs_cents"] / 100
    result["approx_inventory_turnover"] = result.apply(
        lambda row: _ratio(row.estimated_cogs_cents,
                           row.average_inventory_value_cents), axis=1)
    return result.sort_values(keys).reset_index(drop=True)


def calculate_overall_kpis(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sales, inventory = data["sales_fact"], data["inventory_fact"]
    revenue = int(sales["revenue_cents"].sum())
    orders = int(sales["order_id"].nunique())
    units = int(sales["quantity"].sum())
    stockouts = int(inventory["stockout_flag"].sum())
    rows = len(inventory)
    cogs = int(inventory["estimated_cogs_cents"].sum())
    weekly_values = inventory.groupby("week_start")["inventory_value_cents"].sum()
    average_value = float(weekly_values.mean())
    metrics = [
        ("Synthetic Revenue", revenue / 100, "currency", "sales.revenue", "Synthetic prices"),
        ("Synthetic Orders", orders, "orders", "sales.order_id", "Single-item orders"),
        ("Units Sold", units, "units", "sales.quantity", "Reconciled to inventory"),
        ("Synthetic AOV Proxy", _ratio(revenue, orders * 100), "currency/order",
         "sales", "Single-item orders, not customer baskets"),
        ("Synthetic Average Selling Price", _ratio(revenue, units * 100),
         "currency/unit", "sales", "Discounted synthetic price"),
        ("Stockout Rate", _ratio(stockouts, rows), "proportion",
         "inventory.stockout_flag", "Weekly inventory record-based"),
        ("Record-Based Fill Rate Proxy", 1 - _ratio(stockouts, rows), "proportion",
         "inventory.stockout_flag", "Not order fulfillment fill rate"),
        ("Lost Sales Units", int(inventory["lost_sales_units"].sum()), "units",
         "inventory.lost_sales_units", "Synthetic estimate"),
        ("Estimated Lost Sales Value",
         int(inventory["estimated_lost_sales_value_cents"].sum()) / 100, "currency",
         "inventory + products.unit_price", "Catalog-price estimate"),
        ("Spoilage Units", int(inventory["spoilage_units"].sum()), "units",
         "inventory.spoilage_units", "Synthetic inventory"),
        ("Estimated Spoilage Cost",
         int(inventory["estimated_spoilage_cost_cents"].sum()) / 100, "currency",
         "inventory + products.unit_cost", "Synthetic unit-cost estimate"),
        ("Approx Inventory Turnover", _ratio(cogs, average_value), "ratio",
         "inventory + products.unit_cost", "52 weekly closing-value averages; not audited"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "unit", "source", "caveat"])


def calculate_monthly_kpis(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sales, inventory = data["sales_fact"], data["inventory_fact"]
    monthly = _sales_aggregate(sales, ["month"])
    first_day = inventory["week_start"].min()
    last_day = inventory["week_start"].max() + pd.Timedelta(days=6)
    weeks = inventory["week_start"].drop_duplicates().sort_values()
    if (weeks.diff().dropna() != pd.Timedelta(days=7)).any():
        raise ValueError("Inventory week coverage contains gaps; month completeness is unknown")
    monthly["is_complete_month"] = monthly["month"].map(
        lambda month: (pd.Period(month).start_time >= first_day and
                       pd.Period(month).end_time.normalize() <= last_day))
    monthly["synthetic_revenue"] = monthly["revenue_cents"] / 100
    monthly["synthetic_aov_proxy"] = monthly.apply(
        lambda row: _ratio(row.revenue_cents, row.synthetic_orders * 100), axis=1)
    monthly["average_selling_price"] = monthly.apply(
        lambda row: _ratio(row.revenue_cents, row.units_sold * 100), axis=1)
    monthly["mom_revenue_growth"] = math.nan
    monthly["mom_units_growth"] = math.nan
    for index in range(1, len(monthly)):
        previous, current = monthly.iloc[index - 1], monthly.iloc[index]
        adjacent = pd.Period(current.month).ordinal - pd.Period(previous.month).ordinal == 1
        if adjacent and previous.is_complete_month and current.is_complete_month:
            monthly.loc[index, "mom_revenue_growth"] = _ratio(
                current.revenue_cents - previous.revenue_cents, previous.revenue_cents)
            monthly.loc[index, "mom_units_growth"] = _ratio(
                current.units_sold - previous.units_sold, previous.units_sold)
    return monthly[["month", "is_complete_month", "synthetic_revenue",
                    "synthetic_orders", "units_sold", "synthetic_aov_proxy",
                    "average_selling_price", "mom_revenue_growth", "mom_units_growth"]]


def calculate_latest_inventory_snapshot(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    inventory = data["inventory_fact"]
    latest = inventory.sort_values(["store_id", "product_id", "week_start"]).drop_duplicates(
        ["store_id", "product_id"], keep="last"
    ).copy()
    latest["inventory_value"] = latest["inventory_value_cents"] / 100
    latest["week_start"] = latest["week_start"].dt.strftime("%Y-%m-%d")
    return latest[["store_id", "store_name", "region", "product_id", "product_name",
                   "category", "supplier_id", "week_start", "closing_stock",
                   "reorder_point", "safety_stock", "stockout_flag", "inventory_value"]
                  ].sort_values(["store_id", "product_id"]).reset_index(drop=True)


def calculate_product_kpis(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = data["products"][["product_id", "product_name", "category", "supplier_id"]]
    result = _dimension(data, ["product_id"], base)
    result["revenue_rank"] = result["synthetic_revenue"].rank(
        method="min", ascending=False).astype(int)
    result["units_rank"] = result["units_sold"].rank(
        method="min", ascending=False).astype(int)
    return result


def calculate_category_kpis(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = data["products"][["category"]].drop_duplicates()
    result = _dimension(data, ["category"], base)
    result["synthetic_revenue_share"] = result["revenue_cents"] / result["revenue_cents"].sum()
    result["units_share"] = result["units_sold"] / result["units_sold"].sum()
    return result


def calculate_region_kpis(data: dict[str, pd.DataFrame],
                          snapshot: pd.DataFrame) -> pd.DataFrame:
    base = data["stores"][["region"]].drop_duplicates()
    result = _dimension(data, ["region"], base)
    result["synthetic_revenue_share"] = result["revenue_cents"] / result["revenue_cents"].sum()
    latest = snapshot.groupby("region").agg(
        latest_inventory_units=("closing_stock", "sum"),
        latest_inventory_value=("inventory_value", "sum")).reset_index()
    return result.merge(latest, on="region", how="left", validate="one_to_one")


def calculate_store_kpis(data: dict[str, pd.DataFrame],
                         snapshot: pd.DataFrame) -> pd.DataFrame:
    base = data["stores"][["store_id", "store_name", "region", "store_type"]]
    result = _dimension(data, ["store_id"], base)
    latest = snapshot.groupby("store_id").agg(
        latest_inventory_units=("closing_stock", "sum"),
        latest_inventory_value=("inventory_value", "sum")).reset_index()
    return result.merge(latest, on="store_id", how="left", validate="one_to_one")


def calculate_supplier_kpis(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = data["suppliers"][["supplier_id", "supplier_name",
                               "avg_lead_time_days", "reliability_score"]].copy()
    counts = data["products"].groupby("supplier_id").size().rename("product_count")
    base["product_count"] = base["supplier_id"].map(counts).fillna(0).astype(int)
    return _dimension(data, ["supplier_id"], base)


def _public(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].copy()


def build_kpi_outputs(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    snapshot = calculate_latest_inventory_snapshot(data)
    product = calculate_product_kpis(data)
    category = calculate_category_kpis(data)
    region = calculate_region_kpis(data, snapshot)
    store = calculate_store_kpis(data, snapshot)
    supplier = calculate_supplier_kpis(data)
    return {
        "overall_kpi": calculate_overall_kpis(data),
        "monthly_kpi": calculate_monthly_kpis(data),
        "product_kpi": _public(product, [
            "product_id", "product_name", "category", "supplier_id", "synthetic_revenue",
            "units_sold", "synthetic_orders", "average_selling_price", "stockout_rate",
            "lost_sales_units", "estimated_lost_sales_value", "spoilage_units",
            "estimated_spoilage_cost", "approx_inventory_turnover", "revenue_rank",
            "units_rank"]),
        "category_kpi": _public(category, [
            "category", "synthetic_revenue", "synthetic_revenue_share", "units_sold",
            "units_share", "synthetic_orders", "average_selling_price", "stockout_rate",
            "lost_sales_units", "estimated_lost_sales_value", "spoilage_units",
            "estimated_spoilage_cost", "approx_inventory_turnover"]),
        "region_kpi": _public(region, [
            "region", "synthetic_revenue", "synthetic_revenue_share", "units_sold",
            "synthetic_orders", "synthetic_aov_proxy", "average_selling_price",
            "stockout_rate", "lost_sales_units", "estimated_lost_sales_value",
            "latest_inventory_units", "latest_inventory_value"]),
        "store_kpi": _public(store, [
            "store_id", "store_name", "region", "store_type", "synthetic_revenue",
            "units_sold", "synthetic_orders", "synthetic_aov_proxy", "stockout_rate",
            "latest_inventory_units", "latest_inventory_value"]),
        "supplier_kpi": _public(supplier, [
            "supplier_id", "supplier_name", "product_count", "avg_lead_time_days",
            "reliability_score", "synthetic_revenue", "units_sold", "stockout_rate",
            "lost_sales_units", "estimated_lost_sales_value"]),
        "latest_inventory_snapshot": snapshot,
    }


def _sql_queries() -> dict[int, str]:
    source = (ROOT / "sql" / "business_analysis.sql").read_text(encoding="utf-8")
    markers = list(re.finditer(r"(?m)^-- Q(\d{2}) [^\n]+\n", source))
    return {int(marker.group(1)): source[marker.end():(
        markers[index + 1].start() if index + 1 < len(markers) else len(source)
    )].strip() for index, marker in enumerate(markers)}


def validate_kpi_results(data: dict[str, pd.DataFrame],
                         outputs: dict[str, pd.DataFrame],
                         database: Path = DATABASE) -> dict[str, str]:
    overall = outputs["overall_kpi"].set_index("metric")["value"]
    revenue_cents = round(float(overall["Synthetic Revenue"]) * 100)
    units = int(overall["Units Sold"])
    for name in ("product_kpi", "category_kpi", "region_kpi"):
        frame = outputs[name]
        if round(frame["synthetic_revenue"].sum() * 100) != revenue_cents:
            raise ValueError(f"{name}: revenue reconciliation failed")
        if int(frame["units_sold"].sum()) != units:
            raise ValueError(f"{name}: units reconciliation failed")
    if int(outputs["product_kpi"]["synthetic_orders"].sum()) != int(overall["Synthetic Orders"]):
        raise ValueError("Single-item product order reconciliation failed")
    if units != int(data["inventory_fact"]["units_sold"].sum()):
        raise ValueError("Sales/inventory units reconciliation failed")
    for name in ("category_kpi", "region_kpi"):
        share = outputs[name]["synthetic_revenue_share"].sum()
        if not math.isclose(share, 1.0, abs_tol=1e-10):
            raise ValueError(f"{name}: revenue shares do not total one")
    snapshot = outputs["latest_inventory_snapshot"]
    if snapshot.duplicated(["store_id", "product_id"]).any():
        raise ValueError("Latest inventory snapshot key is not unique")
    if len(snapshot) != len(data["inventory_fact"][["store_id", "product_id"]].drop_duplicates()):
        raise ValueError("Latest inventory snapshot is missing store/product pairs")
    with sqlite3.connect(database) as connection:
        queries = _sql_queries()
        sql = {number: pd.read_sql_query(queries[number], connection)
               for number in (1, 2, 3, 4, 5, 6, 7, 9)}
    monthly = outputs["monthly_kpi"].set_index("month")
    for number, field in ((1, "synthetic_revenue"), (2, "synthetic_orders"),
                          (3, "units_sold")):
        for row in sql[number].itertuples(index=False):
            expected = monthly.loc[row.month, field]
            observed = getattr(row, field)
            if number == 1:
                if round(expected * 100) != round(observed * 100):
                    raise ValueError(f"Q{number:02d}: monthly revenue differs for {row.month}")
            elif int(expected) != int(observed):
                raise ValueError(f"Q{number:02d}: monthly {field} differs for {row.month}")
    for number, name, key in ((4, "product_kpi", "product_id"),
                              (5, "category_kpi", "category"),
                              (6, "region_kpi", "region")):
        left = outputs[name].set_index(key)
        right = sql[number].set_index(key)
        if set(left.index) != set(right.index):
            raise ValueError(f"Q{number:02d}: dimension keys differ")
        for member in left.index:
            if (round(left.loc[member, "synthetic_revenue"] * 100) !=
                    round(right.loc[member, "synthetic_revenue"] * 100) or
                    int(left.loc[member, "units_sold"]) != int(right.loc[member, "units_sold"])):
                raise ValueError(f"Q{number:02d}: {member} differs")
    for row in sql[7].itertuples(index=False):
        expected = monthly.loc[row.month]
        if bool(row.is_complete_month) != bool(expected.is_complete_month):
            raise ValueError(f"Q07: month completeness differs for {row.month}")
        growth = expected.mom_revenue_growth
        if pd.isna(growth) != pd.isna(row.growth_pct):
            raise ValueError(f"Q07: MoM availability differs for {row.month}")
        if pd.notna(growth) and not math.isclose(round(growth * 100, 2),
                                                 row.growth_pct, abs_tol=0.01):
            raise ValueError(f"Q07: MoM differs for {row.month}")
    sql_stockout = sql[9].iloc[0]
    if int(sql_stockout.inventory_rows) != len(data["inventory_fact"]) or (
        not math.isclose(float(overall["Stockout Rate"]) * 100,
                         float(sql_stockout.stockout_rate_pct), abs_tol=0.0051)
    ):
        raise ValueError("Q09: stockout rate differs")
    return {key: "PASS" for key in (
        "revenue_reconciliation", "units_reconciliation",
        "revenue_share_reconciliation", "single_item_order_reconciliation",
        "latest_snapshot_uniqueness", "sql_pandas_reconciliation")}


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    display = frame.copy()
    for column in display.columns:
        if column in MONEY_COLUMNS:
            display[column] = display[column].map(
                lambda value: "" if pd.isna(value) else f"{value:.2f}")
        elif column in RATE_COLUMNS or column == "approx_inventory_turnover":
            display[column] = display[column].map(
                lambda value: "" if pd.isna(value) else f"{value:.8f}")
    if path.name == "overall_kpi.csv":
        display["value"] = [
            ("" if pd.isna(value) else f"{value:.2f}" if unit.startswith("currency")
             else f"{value:.8f}" if unit in ("proportion", "ratio") else str(int(value)))
            for value, unit in zip(frame["value"], frame["unit"])
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    display.to_csv(temporary, index=False, lineterminator="\n")
    temporary.replace(path)


def export_kpi_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    for name, frame in outputs.items():
        _write_csv(PROCESSED / f"{name}.csv", frame)


def _bar_chart(frame: pd.DataFrame, label: str, value: str, title: str,
               axis_label: str, filename: str, *, million: bool = False) -> None:
    values = frame[value] / 1_000_000 if million else frame[value]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(frame[label], values, color="#2377A5")
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.set_title(title)
    ax.set_xlabel(axis_label)
    fig.tight_layout()
    fig.savefig(CHARTS / filename, dpi=150)
    plt.close(fig)


def generate_charts(outputs: dict[str, pd.DataFrame]) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    monthly = outputs["monthly_kpi"]
    monthly = monthly[monthly["is_complete_month"]]
    for value, title, ylabel, filename, million in (
        ("synthetic_revenue", "Monthly Synthetic Revenue — Complete Months",
         "Synthetic revenue (millions)", "monthly_revenue_trend.png", True),
        ("units_sold", "Monthly Units Sold — Complete Months",
         "Units sold", "monthly_units_sold_trend.png", False),
    ):
        fig, ax = plt.subplots(figsize=(11, 5))
        series = monthly[value] / 1_000_000 if million else monthly[value]
        ax.plot(monthly["month"], series, marker="o", color="#2377A5")
        ax.set_ylim(bottom=0)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Month")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(CHARTS / filename, dpi=150)
        plt.close(fig)
    product = outputs["product_kpi"].nlargest(10, "synthetic_revenue")
    _bar_chart(product, "product_name", "synthetic_revenue",
               "Top 10 Products by Synthetic Revenue", "Synthetic revenue (millions)",
               "product_revenue_ranking.png", million=True)
    category = outputs["category_kpi"]
    _bar_chart(category.sort_values("synthetic_revenue_share", ascending=False),
               "category", "synthetic_revenue_share", "Category Synthetic Revenue Share",
               "Share of synthetic revenue (0–1)", "category_revenue_share.png")
    region = outputs["region_kpi"].sort_values("synthetic_revenue", ascending=False)
    _bar_chart(region, "region", "synthetic_revenue", "Regional Synthetic Revenue",
               "Synthetic revenue (millions)", "regional_sales_comparison.png",
               million=True)
    _bar_chart(category.sort_values("stockout_rate", ascending=False),
               "category", "stockout_rate", "Category Weekly Record Stockout Rate",
               "Share of inventory records (0–1)", "category_stockout_rate.png")
    _bar_chart(category.sort_values("approx_inventory_turnover", ascending=False),
               "category", "approx_inventory_turnover", "Approximate Inventory Turnover",
               "Estimated COGS / average weekly closing value",
               "inventory_turnover_by_category.png")


def _dictionary_text(outputs: dict[str, pd.DataFrame]) -> str:
    rows = [
        ("Synthetic Revenue", "Generated sales value", "sales", "SUM(revenue)", "all sales or selected dimension", "Transaction prices include synthetic discounts."),
        ("Synthetic Orders", "Generated single-item orders", "sales", "COUNT(DISTINCT order_id)", "all sales or selected dimension", "One order_id is one product row, not a customer basket."),
        ("Units Sold", "Sold units", "sales; inventory", "SUM(sales.quantity)", "all sales or selected dimension", "Reconciles to SUM(inventory.units_sold)."),
        ("Synthetic AOV Proxy", "Value per generated order", "sales", "Synthetic Revenue / Synthetic Orders", "all sales, region, store or month", "Synthetic average single-item order value; not customer basket AOV."),
        ("Synthetic Average Selling Price", "Generated value per unit", "sales", "Synthetic Revenue / Units Sold", "all sales or selected dimension", "Includes generated 0–5% discounts."),
        ("Stockout Rate", "Share of weekly records flagged stockout", "inventory", "SUM(stockout_flag) / COUNT(records)", "week × store × product, then selected dimension", "Record-based; not closing_stock = 0 or an order fill rate."),
        ("Record-Based Fill Rate Proxy", "Complement of record stockout rate", "inventory", "1 - Stockout Rate", "all weekly inventory records", "Not actual order fulfillment."),
        ("Lost Sales Units", "Estimated unserved units", "inventory", "SUM(lost_sales_units)", "weekly inventory records", "Synthetic estimate."),
        ("Estimated Lost Sales Value", "Catalog-price value of estimated lost units", "inventory; products", "SUM(lost_sales_units × unit_price)", "weekly inventory records", "Estimate uses catalog price, not transaction price."),
        ("Spoilage Units", "Recorded spoiled units", "inventory", "SUM(spoilage_units)", "weekly inventory records", "Synthetic inventory."),
        ("Estimated Spoilage Cost", "Cost estimate of spoiled units", "inventory; products", "SUM(spoilage_units × unit_cost)", "weekly inventory records", "Uses synthetic master unit cost."),
        ("Estimated COGS", "Cost estimate of units sold", "inventory; products", "SUM(units_sold × unit_cost)", "weekly inventory records", "Not audited COGS."),
        ("Approx Inventory Turnover", "Analytical stock turnover proxy", "inventory; products", "Estimated COGS / MEAN(weekly SUM(closing_stock × unit_cost))", "all observed weeks by dimension", "Weekly closing values and synthetic costs; not audited financial turnover."),
        ("Synthetic Revenue Share", "Dimension share of generated value", "sales", "Dimension Synthetic Revenue / Overall Synthetic Revenue", "category or region", "All observed sales, including partial edge months."),
        ("Units Share", "Category share of sold units", "sales", "Category Units Sold / Overall Units Sold", "category", "All observed sales."),
        ("Revenue MoM Growth", "Change between adjacent complete calendar months", "sales; inventory coverage", "(current revenue - previous revenue) / previous revenue", "month", "NULL for partial months, first complete month, or zero denominator."),
        ("Units MoM Growth", "Change between adjacent complete calendar months", "sales; inventory coverage", "(current units - previous units) / previous units", "month", "Same completeness and denominator rule."),
        ("Latest Inventory Units", "Latest recorded stock", "inventory", "SUM(latest closing_stock by store_id + product_id)", "store or region", "Weekly closing snapshot."),
        ("Latest Inventory Value", "Cost value of latest stock", "inventory; products", "SUM(latest closing_stock × unit_cost)", "store or region", "Synthetic master cost."),
        ("Supplier Product Count", "Catalog products linked to supplier", "products", "COUNT(product_id)", "supplier", "Product master count, not procurement volume."),
        ("Supplier Lead Time", "Master-data average lead time", "suppliers", "avg_lead_time_days", "supplier", "Static synthetic attribute; no delivery history."),
        ("Supplier Reliability Score", "Master-data reliability score", "suppliers", "reliability_score", "supplier", "Static synthetic attribute; not calculated from purchase transactions."),
        ("Complete Month Flag", "Calendar month fully covered by inventory weeks", "inventory.week_start", "All calendar days lie within contiguous observed inventory-week coverage", "month", "An observed sales date alone does not prove full coverage."),
        ("Revenue and Units Rank", "Product position by revenue or units", "sales", "Descending rank with minimum rank for ties", "product", "Based on synthetic sales."),
    ]
    monthly = outputs["monthly_kpi"]
    complete = monthly.loc[monthly["is_complete_month"], "month"].tolist()
    partial = monthly.loc[~monthly["is_complete_month"], "month"].tolist()
    lines = [
        "# KPI Dictionary", "",
        "All monetary values use the dataset's synthetic currency units. CSV ratios are proportions from 0 to 1; MoM growth is a signed proportion. Missing denominators produce blank CSV cells.", "",
        f"Complete calendar months are determined from contiguous inventory-week coverage, not from the presence of an order on every day. Complete: {', '.join(complete)}. Partial: {', '.join(partial)}.", "",
        "| KPI Name | Business Meaning | Source Table | Formula | Grain | Caveat / Limitation |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.extend(["", "Sales and inventory are aggregated independently before dimensional merging. Supplier stockout association does not establish supplier causation. Inventory accounting semantics for receipts and opening stock remain unresolved.", ""])
    return "\n".join(lines)


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _insights_text(outputs: dict[str, pd.DataFrame],
                   data: dict[str, pd.DataFrame]) -> str:
    overall = outputs["overall_kpi"].set_index("metric")["value"]
    monthly = outputs["monthly_kpi"]
    complete = monthly[monthly["is_complete_month"]]
    if complete.empty:
        raise ValueError("Business insights require at least one complete calendar month")
    first_sale = data["sales_fact"]["order_date"].min().strftime("%Y-%m-%d")
    last_sale = data["sales_fact"]["order_date"].max().strftime("%Y-%m-%d")
    weeks = data["inventory_fact"]["week_start"].nunique()
    first_week = data["inventory_fact"]["week_start"].min().strftime("%Y-%m-%d")
    complete_label = ", ".join(complete["month"].tolist())
    partial_label = ", ".join(monthly.loc[~monthly["is_complete_month"], "month"].tolist())
    product = outputs["product_kpi"]
    category = outputs["category_kpi"]
    region = outputs["region_kpi"]
    store = outputs["store_kpi"]
    supplier = outputs["supplier_kpi"]
    top_product = product.nlargest(1, "synthetic_revenue").iloc[0]
    top_units = product.nlargest(1, "units_sold").iloc[0]
    high_stockout = product.nlargest(1, "stockout_rate").iloc[0]
    lost_product = product.nlargest(1, "lost_sales_units").iloc[0]
    top_category = category.nlargest(1, "synthetic_revenue").iloc[0]
    top_region = region.nlargest(1, "synthetic_revenue").iloc[0]
    top_store = store.nlargest(1, "synthetic_revenue").iloc[0]
    supplier_stockout = supplier.nlargest(1, "stockout_rate").iloc[0]
    best = complete.nlargest(1, "synthetic_revenue").iloc[0]
    low = complete.nsmallest(1, "synthetic_revenue").iloc[0]
    gains = complete.dropna(subset=["mom_revenue_growth"])
    if gains.empty:
        raise ValueError("Business insights require an adjacent pair of complete months")
    biggest_gain = gains.nlargest(1, "mom_revenue_growth").iloc[0]
    biggest_drop = gains.nsmallest(1, "mom_revenue_growth").iloc[0]
    lines = [
        "# Business Insights — Phase 2", "",
        "## 1. Executive Summary", "",
        f"**Fact:** Synthetic revenue was {_money(overall['Synthetic Revenue'])} across {int(overall['Synthetic Orders']):,} generated single-item orders and {int(overall['Units Sold']):,} units. The weekly record stockout rate was {_pct(overall['Stockout Rate'])}.",
        "**Interpretation:** These figures describe a synthetic demonstration dataset, not actual company performance.", "",
        "## 2. Analysis Scope", "",
        f"Cumulative KPIs include sales dated {first_sale} through {last_sale}. Inventory covers {weeks} weeks starting {first_week}. Complete calendar months: {complete_label}. Partial months: {partial_label}. A synthetic order contains one product row, so AOV is a single-item proxy.", "",
        "## 3. Sales Performance", "",
        f"**Fact:** Synthetic AOV proxy was {_money(overall['Synthetic AOV Proxy'])}; synthetic average selling price was {_money(overall['Synthetic Average Selling Price'])}. Among complete months, {best['month']} had the highest synthetic revenue ({_money(best['synthetic_revenue'])}) and {low['month']} the lowest ({_money(low['synthetic_revenue'])}).",
        f"**Fact:** The strongest revenue MoM increase was {biggest_gain['month']} ({_pct(biggest_gain['mom_revenue_growth'])}); the weakest was {biggest_drop['month']} ({_pct(biggest_drop['mom_revenue_growth'])}). Both compare complete months.", "",
        "## 4. Inventory Performance", "",
        f"**Fact:** Lost sales units were {int(overall['Lost Sales Units']):,}, with estimated catalog-price value {_money(overall['Estimated Lost Sales Value'])}. Spoilage units were {int(overall['Spoilage Units']):,}, with estimated cost {_money(overall['Estimated Spoilage Cost'])}. Approximate inventory turnover was {overall['Approx Inventory Turnover']:.2f}.",
        "**Interpretation:** The turnover ratio is an analytical proxy based on weekly closing stock and synthetic unit costs; it is not an audited financial ratio.", "",
        "## 5. Product and Category Insights", "",
        f"**Fact:** {top_product['product_name']} led product synthetic revenue ({_money(top_product['synthetic_revenue'])}); {top_units['product_name']} led units ({int(top_units['units_sold']):,}). {high_stockout['product_name']} had the highest weekly record stockout rate ({_pct(high_stockout['stockout_rate'])}); {lost_product['product_name']} had the most lost sales units ({int(lost_product['lost_sales_units']):,}).",
        f"**Fact:** {top_category['category']} led category revenue with {_pct(top_category['synthetic_revenue_share'])} of synthetic revenue and {_pct(top_category['units_share'])} of units.", "",
        "## 6. Regional and Store Insights", "",
        f"**Fact:** {top_region['region']} led regions with synthetic revenue {_money(top_region['synthetic_revenue'])} and {_pct(top_region['synthetic_revenue_share'])} share. {top_store['store_name']} led stores with {_money(top_store['synthetic_revenue'])}. Latest {top_region['region']} inventory held {int(top_region['latest_inventory_units']):,} units valued at {_money(top_region['latest_inventory_value'])}.", "",
        "## 7. Supplier View", "",
        f"**Fact:** Products linked to {supplier_stockout['supplier_name']} had the highest supplier-associated weekly record stockout rate ({_pct(supplier_stockout['stockout_rate'])}). Its product count was {int(supplier_stockout['product_count'])}, static reliability score {supplier_stockout['reliability_score']:.2f}, and static average lead time {int(supplier_stockout['avg_lead_time_days'])} days.",
        "**Interpretation:** This is an association in synthetic data. No purchase transaction history supports a claim about delivery performance or causation.", "",
        "## 8. Data and Metric Limitations", "",
        "- Transactions, prices and discounts are synthetic; revenue is not actual company revenue.",
        "- Each synthetic order is a single-item row; AOV is not a customer basket measure.",
        f"- Partial calendar months ({partial_label}) are excluded from formal MoM.",
        "- Inventory accounting semantics for opening stock and receipts remain unresolved.",
        "- Supplier reliability and lead time are static synthetic attributes.",
        "- Stockout and fill rate use weekly record flags, not orders; turnover is approximate.", "",
        "## 9. Implications for Phase 3", "",
        "The reconciled historical sales quantities by order date, inventory week, store and product provide a consistent input base for later forecasting work. No forecasting model is trained in Phase 2.", "",
    ]
    return "\n".join(lines)


def write_reports(outputs: dict[str, pd.DataFrame],
                  data: dict[str, pd.DataFrame]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    for name, content in (("KPI_DICTIONARY.md", _dictionary_text(outputs)),
                          ("BUSINESS_INSIGHTS.md", _insights_text(outputs, data))):
        target = REPORTS / name
        temporary = target.with_suffix(".md.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(target)


def run() -> dict[str, object]:
    data = load_analysis_data()
    outputs = build_kpi_outputs(data)
    checks = validate_kpi_results(data, outputs)
    export_kpi_outputs(outputs)
    generate_charts(outputs)
    write_reports(outputs, data)
    return {
        "status": "PASS",
        "complete_months": outputs["monthly_kpi"].loc[
            outputs["monthly_kpi"]["is_complete_month"], "month"].tolist(),
        "partial_months": outputs["monthly_kpi"].loc[
            ~outputs["monthly_kpi"]["is_complete_month"], "month"].tolist(),
        "validation": checks,
        "outputs": list(outputs),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
