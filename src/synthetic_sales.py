"""Generate reproducible synthetic single-item orders from weekly units sold."""

from __future__ import annotations

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd

from .data_cleaning import PROCESSED, RAW, INVENTORY_KEY


RANDOM_SEED = 42
CENT = Decimal("0.01")
SALES_COLUMNS = (
    "order_id", "order_date", "week_start", "store_id", "product_id",
    "quantity", "catalog_unit_price", "transaction_unit_price", "revenue",
    "synthetic_flag",
)


def _cents(value: object) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1")))


def generate_sales(inventory: pd.DataFrame, products: pd.DataFrame) -> bytes:
    rng = np.random.default_rng(RANDOM_SEED)
    prices = {str(row.product_id): Decimal(str(row.unit_price)).quantize(CENT)
              for row in products.itertuples(index=False)}
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(SALES_COLUMNS)
    next_order = 1
    for row in inventory.sort_values(list(INVENTORY_KEY)).itertuples(index=False):
        remaining = int(row.units_sold)
        catalog = prices[str(row.product_id)]
        if catalog <= 0:
            raise ValueError(f"Nonpositive catalog price: {row.product_id}")
        week_start = pd.Timestamp(row.week_start).date()
        while remaining:
            quantity = int(rng.integers(1, min(10, remaining) + 1))
            day = int(rng.integers(0, 7))
            discount_basis_points = int(rng.integers(0, 501))  # 0 to 5 percent
            price = (catalog * Decimal(10000 - discount_basis_points) / Decimal(10000)).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            revenue = price * quantity
            writer.writerow((
                f"ORD{next_order:09d}", (week_start + timedelta(days=day)).isoformat(),
                week_start.isoformat(), row.store_id, row.product_id, quantity,
                f"{catalog:.2f}", f"{price:.2f}", f"{revenue:.2f}", 1,
            ))
            remaining -= quantity
            next_order += 1
    return stream.getvalue().encode("utf-8")


def validate_sales(sales: pd.DataFrame, inventory: pd.DataFrame,
                   products: pd.DataFrame) -> dict:
    if sales.empty or sales["order_id"].isna().any() or sales["order_id"].duplicated().any():
        raise ValueError("Sales order_id is missing or duplicated")
    if not (sales["synthetic_flag"] == 1).all():
        raise ValueError("All sales rows must be marked synthetic")
    if (sales["quantity"] <= 0).any():
        raise ValueError("Sales quantity must be positive")
    if (sales[["catalog_unit_price", "transaction_unit_price", "revenue"]] <= 0).any().any():
        raise ValueError("Sales price and revenue must be positive")
    dates = pd.to_datetime(sales["order_date"], format="%Y-%m-%d", errors="coerce")
    weeks = pd.to_datetime(sales["week_start"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or weeks.isna().any() or ((dates - weeks).dt.days.between(0, 6) == False).any():
        raise ValueError("Sales order_date falls outside its inventory week")

    product_prices = products.set_index("product_id")["unit_price"]
    expected_price = sales["product_id"].map(product_prices)
    if expected_price.isna().any() or ((sales["catalog_unit_price"] - expected_price).abs() > 0.001).any():
        raise ValueError("Sales catalog price differs from products")
    if (sales["transaction_unit_price"] > sales["catalog_unit_price"]).any() or (
        sales["transaction_unit_price"] < sales["catalog_unit_price"] * 0.95 - 0.01
    ).any():
        raise ValueError("Synthetic transaction discount exceeds 5 percent")
    expected_cents = sales["transaction_unit_price"].map(_cents) * sales["quantity"]
    actual_cents = sales["revenue"].map(_cents)
    if (expected_cents != actual_cents).any():
        raise ValueError("Sales revenue does not equal quantity times transaction price")

    keys = list(INVENTORY_KEY)
    sold = inventory.set_index(keys)["units_sold"]
    generated = sales.groupby(keys)["quantity"].sum()
    if not generated.index.isin(sold.index).all():
        raise ValueError("Sales contain a store/product/week absent from inventory")
    difference = generated.reindex(sold.index, fill_value=0) - sold
    if (difference != 0).any():
        raise ValueError(f"Synthetic sales reconciliation failed: maximum difference {int(difference.abs().max())}")
    return {
        "random_seed": RANDOM_SEED,
        "orders": int(sales["order_id"].nunique()),
        "sales_rows": len(sales),
        "date_min": dates.min().date().isoformat(),
        "date_max": dates.max().date().isoformat(),
        "inventory_combinations": len(sold),
        "matched_combinations": int((difference == 0).sum()),
        "unmatched_combinations": int((difference != 0).sum()),
        "maximum_quantity_difference": int(difference.abs().max()),
        "total_quantity_difference": int(difference.sum()),
        "inventory_units_sold": int(sold.sum()),
        "sales_quantity": int(sales["quantity"].sum()),
        "revenue_cents": int(actual_cents.sum()),
    }


def _write_if_identical_or_new(target: Path, content: bytes) -> None:
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError(f"Existing raw synthetic data differs from deterministic output: {target}")
        return
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(target)


def run() -> dict:
    inventory_path = PROCESSED / "inventory_clean.csv"
    if not inventory_path.is_file():
        raise FileNotFoundError(f"Run python -m src.data_cleaning first: {inventory_path}")
    inventory = pd.read_csv(inventory_path, dtype={"store_id": "string", "product_id": "string"})
    products = pd.read_csv(RAW / "products.csv", dtype={"product_id": "string"})
    content = generate_sales(inventory, products)
    sales = pd.read_csv(io.BytesIO(content), dtype={"order_id": "string", "store_id": "string", "product_id": "string"})
    summary = validate_sales(sales, inventory, products)
    _write_if_identical_or_new(RAW / "sales.csv", content)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    target = PROCESSED / "sales_clean.csv"
    temporary = target.with_suffix(".csv.tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
