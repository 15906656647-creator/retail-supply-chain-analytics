"""Phase 4 boundaries for future forecasts, joins, and inventory rules."""

import numpy as np
import pandas as pd
import pytest

from src import forecasting
from src import inventory_alerts as alerts


def _panel(weeks: int = 35) -> pd.DataFrame:
    dates = pd.date_range("2025-01-06", periods=weeks, freq="7D")
    return pd.DataFrame([
        {"date": date, "store_id": store, "product_id": "P1", "units_sold": offset + index}
        for store, offset in (("S1", 1), ("S2", 101))
        for index, date in enumerate(dates)
    ])


def _join_inputs():
    snapshot = pd.DataFrame({
        "store_id": ["S1", "S2"], "store_name": ["Store 1", "Store 2"],
        "region": ["North", "South"], "product_id": ["P1", "P1"],
        "product_name": ["Product", "Product"], "category": ["Dry", "Dry"],
        "supplier_id": ["SUP1", "SUP1"],
        "week_start": pd.to_datetime(["2025-12-29", "2025-12-29"]),
        "closing_stock": [10, 100], "safety_stock": [2, 2], "reorder_point": [5, 5],
    })
    future = pd.DataFrame({
        "forecast_date": pd.to_datetime(["2026-01-05", "2026-01-05"]),
        "store_id": ["S2", "S1"], "product_id": ["P1", "P1"],
        "forecast_demand": [20.0, 12.0],
    })
    suppliers = pd.DataFrame({
        "supplier_id": ["SUP1"], "supplier_name": ["Supplier"],
        "avg_lead_time_days": [14],
    })
    average = pd.DataFrame({
        "store_id": ["S1", "S2"], "product_id": ["P1", "P1"],
        "average_weekly_demand": [10.0, 10.0],
    })
    return future, snapshot, suppliers, average


@pytest.mark.parametrize(("values", "expected"), [
    ((4, 5, 0, 0, 1), "STOCKOUT_RISK"),
    ((6, 5, 2, 0, 2), "LOW_STOCK"),
    ((10, 2, 0, 10, 2), "LOW_STOCK"),
    ((80, 2, 0, 1, 10), "OVERSTOCK"),
    ((30, 2, 0, 1, 10), "NORMAL"),
    ((1, 2, 0, 10, 0), "STOCKOUT_RISK"),
])
def test_risk_states_and_priority(values, expected):
    status, reason = alerts.classify_risk(*values)
    assert status == expected
    assert reason.strip()


def test_overstock_boundary_and_zero_demand():
    assert alerts.classify_risk(79.9, 1, 0, 0, 10)[0] == "NORMAL"
    assert alerts.classify_risk(80, 1, 0, 0, 10)[0] == "OVERSTOCK"
    assert alerts.classify_risk(20, 0, 0, 1, 0)[0] == "OVERSTOCK"
    assert alerts.classify_risk(0, 0, 0, 0, 0)[0] == "STOCKOUT_RISK"


def test_future_features_use_latest_and_earlier_observations():
    panel = _panel()
    future = forecasting.build_next_week_features(panel).set_index("store_id")
    assert future["date"].eq(panel["date"].max() + pd.Timedelta(days=7)).all()
    assert future["units_sold"].isna().all()
    for store in ("S1", "S2"):
        history = panel.loc[panel["store_id"].eq(store), "units_sold"]
        assert future.loc[store, "lag_1"] == history.iloc[-1]
        assert future.loc[store, "lag_7"] == history.iloc[-7]
        assert future.loc[store, "rolling_mean_7"] == pytest.approx(history.iloc[-7:].mean())
        assert future.loc[store, "rolling_mean_30"] == pytest.approx(history.iloc[-30:].mean())


def test_final_model_trains_on_all_eligible_history(monkeypatch):
    seen = {}

    class Model:
        def predict(self, features):
            assert features.notna().all().all()
            return np.full(len(features), 7.25)

    def train(rows):
        seen["rows"] = len(rows)
        seen["last_date"] = rows["date"].max()
        return Model()

    monkeypatch.setattr(forecasting, "train_random_forest", train)
    result = forecasting.forecast_next_week(_panel())
    assert seen == {"rows": 10, "last_date": _panel()["date"].max()}
    assert len(result) == 2
    assert result["forecast_date"].eq(seen["last_date"] + pd.Timedelta(days=7)).all()
    assert result["forecast_demand"].eq(7.25).all()


def test_negative_future_prediction_is_rejected(monkeypatch):
    class Model:
        def predict(self, features):
            return np.full(len(features), -1.0)

    monkeypatch.setattr(forecasting, "train_random_forest", lambda rows: Model())
    with pytest.raises(ValueError, match="nonnegative"):
        forecasting.forecast_next_week(_panel())


def test_recent_average_uses_four_observed_weeks():
    result = alerts.calculate_average_demand(_panel()).set_index("store_id")
    assert result.loc["S1", "average_weekly_demand"] == pytest.approx(33.5)
    assert result.loc["S2", "average_weekly_demand"] == pytest.approx(133.5)


def test_forecast_join_stays_with_correct_store_and_has_unique_output_key():
    joined = alerts.prepare_alert_dataset(*_join_inputs())
    result = alerts.calculate_inventory_metrics(joined).set_index("store_id")
    assert result.loc["S1", "forecast_demand"] == 12
    assert result.loc["S1", "risk_status"] == "STOCKOUT_RISK"
    assert result.loc["S2", "forecast_demand"] == 20
    assert result.loc["S2", "risk_status"] == "OVERSTOCK"
    assert result["supplier_lead_time_days"].eq(14).all()
    assert not result.reset_index().duplicated(alerts.OUTPUT_KEY).any()


def test_duplicate_supplier_or_forecast_key_is_rejected():
    future, snapshot, suppliers, average = _join_inputs()
    with pytest.raises(ValueError, match="duplicate keys"):
        alerts.prepare_alert_dataset(pd.concat([future, future.iloc[[0]]]), snapshot, suppliers, average)
    with pytest.raises(pd.errors.MergeError):
        alerts.prepare_alert_dataset(future, snapshot, pd.concat([suppliers, suppliers]), average)


def test_forecast_coverage_and_future_date_are_checked():
    future, snapshot, suppliers, average = _join_inputs()
    with pytest.raises(ValueError, match="coverage differ"):
        alerts.prepare_alert_dataset(future.iloc[[0]], snapshot, suppliers, average)
    future["forecast_date"] = pd.Timestamp("2025-12-29")
    with pytest.raises(ValueError, match="week after"):
        alerts.prepare_alert_dataset(future, snapshot, suppliers, average)


def test_negative_stock_forecast_and_safety_are_rejected():
    for position in (0, 1, 2):
        values = [10, 2, 1, 1, 1]
        values[position] = -1
        with pytest.raises(ValueError, match="nonnegative"):
            alerts.classify_risk(*values)


def test_zero_demand_has_no_weeks_of_supply_and_reasons_are_required():
    joined = alerts.prepare_alert_dataset(*_join_inputs())
    joined.loc[joined["store_id"].eq("S2"), "average_weekly_demand"] = 0
    result = alerts.calculate_inventory_metrics(joined)
    zero = result.loc[result["store_id"].eq("S2")].iloc[0]
    assert pd.isna(zero["weeks_of_supply"])
    assert zero["risk_status"] == "OVERSTOCK"
    assert alerts.validate_alerts(result)["key_uniqueness"] == "PASS"
    result.loc[0, "risk_reason"] = " "
    with pytest.raises(ValueError, match="explanation"):
        alerts.validate_alerts(result)


def test_all_one_status_is_rejected():
    joined = alerts.prepare_alert_dataset(*_join_inputs())
    result = alerts.calculate_inventory_metrics(joined)
    result["risk_status"] = "NORMAL"
    with pytest.raises(ValueError, match="one status"):
        alerts.validate_alerts(result)


def test_duplicate_output_key_is_rejected():
    joined = alerts.prepare_alert_dataset(*_join_inputs())
    result = alerts.calculate_inventory_metrics(joined)
    duplicated = pd.concat([result, result.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        alerts.validate_alerts(duplicated)
