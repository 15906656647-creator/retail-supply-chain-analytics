"""Phase 5 grain and cross-phase reconciliation boundaries."""

import pandas as pd
import pytest

from src import powerbi_dataset as bi


@pytest.fixture
def inputs():
    weeks = ("2025-01-06", "2025-01-13")
    sales = pd.DataFrame([
        ["O1", "2025-01-06", weeks[0], "S1", "P1", 2, 10.0, 10.0, 20.0, 1],
        ["O2", "2025-01-07", weeks[0], "S1", "P1", 1, 10.0, 10.0, 10.0, 1],
        ["O3", "2025-01-13", weeks[1], "S2", "P2", 3, 5.0, 5.0, 15.0, 1],
    ], columns=[
        "order_id", "order_date", "week_start", "store_id", "product_id", "quantity",
        "catalog_unit_price", "transaction_unit_price", "revenue", "synthetic_flag",
    ])
    inventory = pd.DataFrame([
        [weeks[0], "S1", "P1", "Food", "U1", 12, 0, 0, 3, 10, 0, 4, 2],
        [weeks[0], "S2", "P2", "Care", "U2", 20, 0, 0, 0, 20, 0, 4, 2],
        [weeks[1], "S1", "P1", "Food", "U1", 3, 0, 0, 0, 0, 1, 4, 2],
        [weeks[1], "S2", "P2", "Care", "U2", 18, 0, 0, 3, 15, 0, 4, 2],
    ], columns=[
        "week_start", "store_id", "product_id", "category", "supplier_id", "opening_stock",
        "units_received_missing_flag", "units_received_clean", "units_sold", "closing_stock",
        "stockout_flag", "reorder_point", "safety_stock",
    ])
    snapshot = inventory.loc[inventory.week_start.eq(weeks[1]), [
        "store_id", "product_id", "week_start", "closing_stock", "stockout_flag",
        "supplier_id", "category", "safety_stock", "reorder_point",
    ]].reset_index(drop=True)
    snapshot["inventory_value"] = [0.0, 45.0]
    forecast = pd.DataFrame([
        [weeks[0], "S1", "P1", 3, 2, 2.5, 3.0],
        [weeks[0], "S2", "P2", 0, 1, -0.5, 0.2],
    ], columns=[
        "date", "store_id", "product_id", "actual_demand", "naive_prediction",
        "linear_regression_prediction", "random_forest_prediction",
    ])
    alerts = pd.DataFrame([
        ["2025-01-20", weeks[1], "S1", "P1", "U1", 0, 1.0, 2, 4, 1.5,
         "STOCKOUT_RISK", "Forecast exceeds current stock"],
        ["2025-01-20", weeks[1], "S2", "P2", "U2", 15, 2.0, 2, 4, 1.5,
         "NORMAL", "No risk trigger"],
    ], columns=[
        "forecast_date", "inventory_week_start", "store_id", "product_id", "supplier_id",
        "current_stock", "forecast_demand", "safety_stock", "reorder_point",
        "average_weekly_demand", "risk_status", "risk_reason",
    ])
    return {
        "sales": sales, "inventory": inventory, "snapshot": snapshot,
        "forecast": forecast, "alerts": alerts,
        "overall": pd.DataFrame({
            "metric": ["Synthetic Revenue", "Synthetic Orders", "Units Sold", "Stockout Rate"],
            "value": [45.0, 3, 6, 0.25],
        }),
        "stores": pd.DataFrame({
            "store_id": ["S1", "S2"], "store_name": ["Store 1", "Store 2"],
            "region": ["North", "South"], "store_type": ["Small", "Large"],
        }),
        "products": pd.DataFrame({
            "product_id": ["P1", "P2"], "product_name": ["Item 1", "Item 2"],
            "category": ["Food", "Care"], "supplier_id": ["U1", "U2"],
            "unit_cost": [6.0, 3.0], "unit_price": [10.0, 5.0],
        }),
        "suppliers": pd.DataFrame({
            "supplier_id": ["U1", "U2"], "supplier_name": ["Supplier 1", "Supplier 2"],
            "avg_lead_time_days": [3, 5], "reliability_score": [0.8, 0.9],
        }),
    }


def test_order_grain_preserves_sales_without_inventory_fanout(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    result = bi.validate_powerbi_dataset(dataset, inputs)
    assert len(dataset) == 3
    assert not dataset.duplicated(bi.SALES_KEY).any()
    assert dataset.loc[dataset.product_id.eq("P1"), "revenue"].sum() == 30
    assert "closing_stock" not in dataset and "forecast_demand" not in dataset
    assert result["revenue_cents"] == 4500
    assert result["orders_count"] == 3
    assert result["units_count"] == 6
    assert result["inventory_rows"] == 4
    assert result["alert_rows"] == 2


def test_duplicate_dimension_key_is_rejected(inputs):
    inputs["stores"] = pd.concat([inputs["stores"], inputs["stores"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate key"):
        bi.prepare_sales_fact(inputs)


def test_unknown_dimension_reference_is_rejected(inputs):
    inputs["sales"].loc[0, "product_id"] = "UNKNOWN"
    with pytest.raises(ValueError, match="dimension join"):
        bi.prepare_sales_fact(inputs)


def test_duplicate_order_key_is_rejected(inputs):
    inputs["sales"].loc[1, "order_id"] = "O1"
    with pytest.raises(ValueError, match="duplicate key"):
        bi.prepare_sales_fact(inputs)


def test_phase2_sales_reconciliation_fails_on_changed_total(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["overall"].loc[inputs["overall"].metric.eq("Synthetic Revenue"), "value"] = 44.99
    with pytest.raises(ValueError, match="Sales reconciliation"):
        bi.validate_powerbi_dataset(dataset, inputs)


def test_snapshot_and_alert_stock_must_reconcile(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["alerts"].loc[0, "current_stock"] = 1
    with pytest.raises(ValueError, match="differs from snapshot"):
        bi.validate_powerbi_dataset(dataset, inputs)


def test_latest_inventory_value_uses_product_cost(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["snapshot"].loc[1, "inventory_value"] = 44.0
    with pytest.raises(ValueError, match="inventory_value differs"):
        bi.validate_powerbi_dataset(dataset, inputs)


def test_weekly_sales_inventory_units_must_reconcile_even_when_totals_match(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["inventory"].loc[0, "units_sold"] = 2
    inputs["inventory"].loc[2, "units_sold"] = 1
    with pytest.raises(ValueError, match="weekly store/product units"):
        bi.validate_powerbi_dataset(dataset, inputs)


def test_forecast_key_and_historical_actual_are_checked(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["forecast"] = pd.concat([inputs["forecast"], inputs["forecast"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate key"):
        bi.validate_powerbi_dataset(dataset, inputs)
    inputs["forecast"] = inputs["forecast"].iloc[:2].copy()
    inputs["forecast"].loc[0, "actual_demand"] = 4
    with pytest.raises(ValueError, match="historical actuals"):
        bi.validate_powerbi_dataset(dataset, inputs)


def test_alert_key_and_risk_status_are_checked(inputs):
    dataset = bi.prepare_sales_fact(inputs)
    inputs["alerts"] = pd.concat([inputs["alerts"], inputs["alerts"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate key"):
        bi.validate_powerbi_dataset(dataset, inputs)
    inputs["alerts"] = inputs["alerts"].iloc[:2].copy()
    inputs["alerts"].loc[0, "risk_status"] = "UNKNOWN"
    with pytest.raises(ValueError, match="invalid risk status"):
        bi.validate_powerbi_dataset(dataset, inputs)
