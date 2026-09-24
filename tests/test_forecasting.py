"""Boundary checks for weekly synthetic-demand forecasting."""

import math

import numpy as np
import pandas as pd
import pytest

from src import forecasting as forecast


def _panel(weeks: int = 35) -> pd.DataFrame:
    dates = pd.date_range("2025-01-06", periods=weeks, freq="7D")
    return pd.DataFrame([
        {"date": day, "store_id": "S1", "product_id": product, "units_sold": offset + i}
        for product, offset in (("P1", 0), ("P2", 100))
        for i, day in enumerate(dates)
    ])


def test_zero_sales_week_and_weekly_reconciliation():
    inventory = pd.DataFrame({
        "week_start": pd.to_datetime(["2025-01-06", "2025-01-13", "2025-01-20"]),
        "store_id": ["S1"] * 3,
        "product_id": ["P1"] * 3,
        "units_sold": [3, 0, 2],
    })
    sales = pd.DataFrame({
        "order_date": pd.to_datetime(["2025-01-09", "2025-01-22"]),
        "week_start": pd.to_datetime(["2025-01-06", "2025-01-20"]),
        "store_id": ["S1", "S1"],
        "product_id": ["P1", "P1"],
        "quantity": [3, 2],
    })
    series = forecast.build_time_series(sales, inventory)
    assert series["units_sold"].tolist() == [3, 0, 2]
    assert series["date"].diff().dropna().eq(pd.Timedelta(days=7)).all()

    broken = inventory.drop(index=1)
    with pytest.raises(ValueError, match="not continuous"):
        forecast.build_time_series(sales, broken)
    another_pair = inventory.copy()
    another_pair["product_id"] = "P2"
    another_pair["units_sold"] = 0
    pair_gap = pd.concat([inventory, another_pair.drop(index=1)], ignore_index=True)
    with pytest.raises(ValueError, match="missing an inventory week"):
        forecast.build_time_series(sales, pair_gap)
    wrong_sales = sales.copy()
    wrong_sales.loc[0, "quantity"] = 4
    with pytest.raises(ValueError, match="reconcile"):
        forecast.build_time_series(wrong_sales, inventory)


def test_lags_and_shifted_rolling_stay_within_each_series():
    features = forecast.create_features(_panel()).set_index(["product_id", "date"])
    day_8 = pd.Timestamp("2025-03-03")
    assert features.loc[("P1", day_8), "lag_1"] == 7
    assert features.loc[("P1", day_8), "lag_7"] == 1
    assert features.loc[("P1", day_8), "rolling_mean_7"] == 4
    assert features.loc[("P2", day_8), "lag_1"] == 107
    assert features.loc[("P2", day_8), "rolling_mean_7"] == 104
    day_30 = pd.Timestamp("2025-08-04")
    assert features.loc[("P1", day_30), "rolling_mean_30"] == pytest.approx(14.5)
    assert math.isnan(features.loc[("P1", pd.Timestamp("2025-07-28")), "rolling_mean_30"])


def test_current_or_future_target_cannot_change_current_features():
    original = _panel()
    target_day = pd.Timestamp("2025-08-04")
    before = forecast.create_features(original).set_index(["product_id", "date"])
    changed = original.copy()
    changed.loc[(changed["product_id"] == "P1") & (changed["date"] >= target_day), "units_sold"] = 9999
    after = forecast.create_features(changed).set_index(["product_id", "date"])
    for name in ("lag_1", "lag_7", "rolling_mean_7", "rolling_mean_30"):
        assert after.loc[("P1", target_day), name] == before.loc[("P1", target_day), name]


def test_split_keeps_entire_dates_in_order():
    eligible = forecast.create_features(_panel()).dropna(subset=forecast.FEATURES)
    train, test = forecast.time_based_split(eligible, train_fraction=0.8)
    assert train["date"].max() < test["date"].min()
    assert set(train["date"]).isdisjoint(test["date"])
    assert train.groupby("date").size().eq(2).all()
    assert test.groupby("date").size().eq(2).all()


def test_mae_and_rmse_use_aligned_observations():
    metrics = forecast.evaluate_predictions(np.array([1, 3, 5]), np.array([2, 3, 1]))
    assert metrics["mae"] == pytest.approx(5 / 3)
    assert metrics["rmse"] == pytest.approx(math.sqrt(17 / 3))
    with pytest.raises(ValueError, match="finite"):
        forecast.evaluate_predictions([1, 2], np.array([1, np.nan]))


def test_results_have_actuals_predictions_and_one_row_per_test_key():
    eligible = forecast.create_features(_panel()).dropna(subset=forecast.FEATURES)
    _, test = forecast.time_based_split(eligible)
    predictions = {
        "naive": forecast.naive_forecast(test),
        "linear_regression": np.ones(len(test)),
        "random_forest": np.ones(len(test)) * 2,
    }
    results = forecast.build_forecast_results(test, predictions)
    assert list(results) == forecast.RESULT_COLUMNS
    assert len(results) == len(test)
    assert results.notna().all().all()
    assert not results.duplicated(["date", "store_id", "product_id"]).any()
    assert results["date"].is_monotonic_increasing


def test_random_forest_seed_repeats_predictions():
    eligible = forecast.create_features(_panel()).dropna(subset=forecast.FEATURES)
    train, test = forecast.time_based_split(eligible)
    first = forecast.train_random_forest(train).predict(test[forecast.FEATURES])
    second = forecast.train_random_forest(train).predict(test[forecast.FEATURES])
    np.testing.assert_array_equal(first, second)
