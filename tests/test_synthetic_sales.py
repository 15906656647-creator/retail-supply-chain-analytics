"""Validate reproducible orders and their source-week accounting."""

import io

import pandas as pd
import pytest

from src import synthetic_sales as synthetic


@pytest.fixture
def inputs():
    inventory = pd.DataFrame({
        "store_id": ["S1", "S1", "S2"],
        "product_id": ["P1", "P1", "P1"],
        "week_start": ["2025-01-06", "2025-01-13", "2025-01-06"],
        "units_sold": [11, 0, 7],
    })
    products = pd.DataFrame({"product_id": ["P1"], "unit_price": [10.00]})
    return inventory, products


def _orders(content):
    return pd.read_csv(io.BytesIO(content), dtype={
        "order_id": "string", "store_id": "string", "product_id": "string",
    })


def test_seed_repeats_bytes_and_orders_reconcile_to_inventory(inputs):
    inventory, products = inputs
    first = synthetic.generate_sales(inventory, products)
    assert first == synthetic.generate_sales(inventory, products)
    sales = _orders(first)
    summary = synthetic.validate_sales(sales, inventory, products)
    assert summary["random_seed"] == synthetic.RANDOM_SEED
    assert summary["inventory_units_sold"] == summary["sales_quantity"] == 18
    assert summary["maximum_quantity_difference"] == 0
    assert summary["matched_combinations"] == 3
    assert sales["order_id"].is_unique
    assert sales["synthetic_flag"].eq(1).all()
    assert sales["quantity"].between(1, 10).all()
    assert sales["revenue"].map(synthetic._cents).eq(
        sales["transaction_unit_price"].map(synthetic._cents) * sales["quantity"]
    ).all()
    day_offset = pd.to_datetime(sales["order_date"]) - pd.to_datetime(sales["week_start"])
    assert day_offset.dt.days.between(0, 6).all()
    assert not sales["week_start"].eq("2025-01-13").any()


@pytest.mark.parametrize(("column", "value", "message"), [
    ("revenue", 999.00, "revenue does not equal"),
    ("order_date", "2025-01-14", "outside its inventory week"),
    ("quantity", 1, "reconciliation failed"),
])
def test_sales_validation_rejects_broken_contract(inputs, column, value, message):
    inventory, products = inputs
    sales = _orders(synthetic.generate_sales(inventory, products))
    if column == "quantity":
        sales.loc[0, column] = sales.loc[0, column] + 1
        sales.loc[0, "revenue"] = (
            sales.loc[0, column] * sales.loc[0, "transaction_unit_price"]
        )
    else:
        sales.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        synthetic.validate_sales(sales, inventory, products)
