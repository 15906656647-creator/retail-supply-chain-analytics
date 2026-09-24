"""Focused boundary checks for the Phase 2 KPI definitions."""

import math

import pandas as pd
import pytest

from src import kpi_analysis as kpi


def test_partial_months_and_zero_denominators():
    weeks = pd.date_range("2025-01-06", "2025-04-28", freq="7D")
    inventory = pd.DataFrame({"week_start": weeks})
    sales = pd.DataFrame({
        "month": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05"],
        "order_id": ["A", "B", "C", "D", "E"],
        "revenue_cents": [1000, 2000, 4000, 0, 1000],
        "quantity": [1, 2, 4, 0, 1],
    })
    monthly = kpi.calculate_monthly_kpis({
        "sales_fact": sales, "inventory_fact": inventory
    }).set_index("month")
    assert monthly["is_complete_month"].to_dict() == {
        "2025-01": False, "2025-02": True, "2025-03": True,
        "2025-04": True, "2025-05": False,
    }
    assert math.isnan(monthly.loc["2025-02", "mom_revenue_growth"])
    assert monthly.loc["2025-03", "mom_revenue_growth"] == 1
    assert monthly.loc["2025-04", "mom_revenue_growth"] == -1
    assert math.isnan(monthly.loc["2025-05", "mom_revenue_growth"])
    assert math.isnan(monthly.loc["2025-04", "average_selling_price"])

    sales.loc[sales["month"] == "2025-03", "revenue_cents"] = 0
    monthly = kpi.calculate_monthly_kpis({
        "sales_fact": sales, "inventory_fact": inventory
    }).set_index("month")
    assert math.isnan(monthly.loc["2025-04", "mom_revenue_growth"])
    assert math.isnan(kpi._ratio(2, 0))


def test_separate_facts_prevent_fanout_and_average_weekly_value():
    sales = pd.DataFrame({
        "product_id": ["P1", "P1"],
        "order_id": ["A", "B"],
        "revenue_cents": [1000, 2000],
        "quantity": [1, 2],
    })
    inventory = pd.DataFrame({
        "product_id": ["P1"] * 3,
        "week_start": pd.to_datetime(["2025-02-03", "2025-02-03", "2025-02-10"]),
        "stockout_flag": [0, 1, 0],
        "lost_sales_units": [0, 1, 0],
        "spoilage_units": [0, 0, 0],
        "estimated_lost_sales_value_cents": [0, 500, 0],
        "estimated_spoilage_cost_cents": [0, 0, 0],
        "estimated_cogs_cents": [200, 300, 500],
        "inventory_value_cents": [1000, 2000, 3000],
    })
    result = kpi._dimension(
        {"sales_fact": sales, "inventory_fact": inventory},
        ["product_id"], pd.DataFrame({"product_id": ["P1"]})
    ).iloc[0]
    assert result.synthetic_revenue == 30
    assert result.synthetic_orders == 2
    assert result.units_sold == 3
    assert result.stockout_rate == pytest.approx(1 / 3)
    assert result.approx_inventory_turnover == pytest.approx(1000 / 3000)


def test_missing_database_has_rebuild_instructions(tmp_path):
    with pytest.raises(FileNotFoundError, match="python -m src.database"):
        kpi.load_analysis_data(tmp_path / "missing.db")
