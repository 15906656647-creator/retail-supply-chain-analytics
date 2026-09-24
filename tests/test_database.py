"""Exercise the real SQLite schema and cross-system reconciliation in memory."""

import sqlite3

import pandas as pd
import pytest

from src import database


@pytest.fixture
def tiny_database():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript((database.ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
    frames = {
        "stores": pd.DataFrame([
            ["S1", "Store 1", "North", "Small"],
        ], columns=["store_id", "store_name", "region", "store_type"]),
        "suppliers": pd.DataFrame([
            ["U1", "Supplier 1", "Packaged Foods", 7, 0.9],
        ], columns=["supplier_id", "supplier_name", "category", "avg_lead_time_days", "reliability_score"]),
        "products": pd.DataFrame([
            ["P1", "Product 1", "Packaged Foods", 4.0, 10.0, "U1"],
        ], columns=["product_id", "product_name", "category", "unit_cost", "unit_price", "supplier_id"]),
        "inventory": pd.DataFrame([
            ["S1", "P1", "Packaged Foods", "2025-01-06", 10, 0, 0, 0, 2, 8, 0, 0, 6, 2, "U1"],
            ["S1", "P1", "Packaged Foods", "2025-01-13", 8, 0, 0, 0, 3, 5, 0, 0, 6, 2, "U1"],
        ], columns=[
            "store_id", "product_id", "category", "week_start", "opening_stock",
            "units_received_raw", "units_received_missing_flag", "units_received_clean",
            "spoilage_units", "closing_stock", "stockout_flag", "lost_sales_units",
            "reorder_point", "safety_stock", "supplier_id",
        ]),
        "sales": pd.DataFrame([
            ["O1", "2025-01-07", "2025-01-06", "S1", "P1", 2, 10.0, 10.0, 20.0, 1],
            ["O2", "2025-01-14", "2025-01-13", "S1", "P1", 3, 10.0, 10.0, 30.0, 1],
        ], columns=[
            "order_id", "order_date", "week_start", "store_id", "product_id", "quantity",
            "catalog_unit_price", "transaction_unit_price", "revenue", "synthetic_flag",
        ]),
    }
    frames["inventory"].insert(8, "units_sold", [2, 3])
    with connection:
        for table in database.TABLES:
            database._insert_frame(connection, table, frames[table])
    try:
        yield connection, frames["inventory"], frames["sales"]
    finally:
        connection.close()


def test_schema_queries_and_sql_pandas_reconciliation(tiny_database):
    connection, inventory, sales = tiny_database
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    queries = database.execute_business_queries(connection)
    assert len(queries) == 18
    checks = database.reconcile_sql_pandas(connection, inventory, sales)
    assert checks["inventory_units_sold"] == {"pandas": 5, "sql": 5}
    assert checks["synthetic_revenue_cents"] == {"pandas": 5000, "sql": 5000}


def test_sql_pandas_reconciliation_detects_changed_revenue(tiny_database):
    connection, inventory, sales = tiny_database
    connection.execute("UPDATE sales SET revenue = 29 WHERE order_id = 'O2'")
    with pytest.raises(ValueError, match="SQL/Pandas reconciliation failed"):
        database.reconcile_sql_pandas(connection, inventory, sales)
