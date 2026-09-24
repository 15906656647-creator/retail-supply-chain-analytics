"""Small Phase 1 fixtures for cleaning and accounting boundaries."""

import pandas as pd
import pytest

from src import data_cleaning as cleaning


@pytest.fixture
def raw_data():
    inventory = pd.DataFrame([
        ["S1", "P1", "packaged foods", "2025-01-06", 10, 0, 1, 2, 7, 0, 0, 5, 2, "U1"],
        ["S1", "P1", " Packaged Foods ", "2025-01-13", 12, 5, 1, 3, 8, 0, 0, 5, 2, "U1"],
        ["S1", "P1", "Packaged Foods", "2025-01-20", 8, pd.NA, 0, 2, 6, 0, 0, 5, 2, "U1"],
    ], columns=[
        "store_id", "product_id", "category", "week_start", "opening_stock",
        "units_received", "spoilage_units", "units_sold", "closing_stock",
        "stockout_flag", "lost_sales_units", "reorder_point", "safety_stock", "supplier_id",
    ]).astype("string")
    inventory = pd.concat([inventory, inventory.iloc[[0]]], ignore_index=True)
    return {
        "inventory_ledger": inventory,
        "stores": pd.DataFrame({"store_id": ["S1"]}).astype("string"),
        "products": pd.DataFrame({
            "product_id": ["P1"], "category": ["Packaged Foods"],
            "supplier_id": ["U1"], "unit_cost": ["4.00"], "unit_price": ["10.00"],
        }).astype("string"),
        "suppliers": pd.DataFrame({
            "supplier_id": ["U1"], "avg_lead_time_days": ["7"],
            "reliability_score": ["0.9"],
        }).astype("string"),
    }


def test_exact_duplicate_only_and_missing_receipts_remain_distinct(raw_data):
    inventory, summary = cleaning.build_clean_inventory(raw_data)
    assert summary["raw_rows"] == 4
    assert summary["raw_duplicate_rows"] == 1
    assert summary["clean_rows"] == 3
    assert summary["clean_duplicate_rows"] == 0
    assert summary["clean_units_received_missing"] == 1
    assert inventory["category"].tolist() == ["Packaged Foods"] * 3
    missing = inventory.loc[inventory["week_start"].eq("2025-01-20")].iloc[0]
    assert pd.isna(missing["units_received_raw"])
    assert pd.isna(missing["units_received_clean"])
    assert missing["units_received_missing_flag"] == 1
    assert inventory.loc[inventory["week_start"].eq("2025-01-06"),
                         "units_received_missing_flag"].iloc[0] == 0


def test_conflicting_composite_key_is_rejected(raw_data):
    different = raw_data["inventory_ledger"].iloc[[0]].copy()
    different["closing_stock"] = "6"
    raw_data["inventory_ledger"] = pd.concat(
        [raw_data["inventory_ledger"], different], ignore_index=True
    )
    with pytest.raises(ValueError, match="Conflicting rows"):
        cleaning.build_clean_inventory(raw_data)


@pytest.mark.parametrize(("date", "message"), [
    ("not-a-date", "invalid dates"),
    ("2025-01-07", "must be a Monday"),
])
def test_invalid_inventory_dates_are_rejected(raw_data, date, message):
    raw_data["inventory_ledger"].loc[0, "week_start"] = date
    with pytest.raises(ValueError, match=message):
        cleaning.build_clean_inventory(raw_data)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("units_sold", "-1", "negative or zero"),
    ("units_sold", "many", "nonnumeric"),
    ("opening_stock", "1.5", "fractional"),
    ("stockout_flag", "2", "outside 0/1"),
])
def test_invalid_numeric_inputs_are_rejected(raw_data, field, value, message):
    raw_data["inventory_ledger"].loc[1, field] = value
    with pytest.raises(ValueError, match=message):
        cleaning.build_clean_inventory(raw_data)


def test_unknown_category_is_rejected(raw_data):
    raw_data["inventory_ledger"].loc[1, "category"] = "Unknown"
    with pytest.raises(ValueError, match="Unmatched category"):
        cleaning.build_clean_inventory(raw_data)


def test_inventory_accounting_reports_known_and_missing_receipts(raw_data):
    inventory, _ = cleaning.build_clean_inventory(raw_data)
    balance = cleaning.validate_inventory_balance(inventory)
    assert balance["rule_a_known_rows"] == 2
    assert balance["rule_a_known_match"] == 1
    assert balance["rule_b_match"] == 3
    assert balance["transition_rows"] == 2
    assert balance["transition_seven_day_gaps"] == 2
    assert balance["transition_known_match"] == 1
    assert balance["transition_missing_receipts"] == 1
    assert balance["transition_missing_zero_difference"] == 1
