-- Phase 1 SQLite schema. All sales are synthetic single-item orders.
CREATE TABLE stores (
    store_id TEXT PRIMARY KEY,
    store_name TEXT NOT NULL,
    region TEXT NOT NULL,
    store_type TEXT NOT NULL
);

CREATE TABLE suppliers (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    category TEXT NOT NULL,
    avg_lead_time_days INTEGER NOT NULL CHECK (avg_lead_time_days >= 0),
    reliability_score REAL NOT NULL CHECK (reliability_score BETWEEN 0 AND 1)
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_cost REAL NOT NULL CHECK (unit_cost >= 0),
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id)
);

CREATE TABLE inventory (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    category TEXT NOT NULL,
    week_start TEXT NOT NULL,
    opening_stock INTEGER NOT NULL CHECK (opening_stock >= 0),
    units_received_raw INTEGER CHECK (units_received_raw >= 0),
    units_received_missing_flag INTEGER NOT NULL CHECK (units_received_missing_flag IN (0, 1)),
    units_received_clean INTEGER CHECK (units_received_clean >= 0),
    spoilage_units INTEGER NOT NULL CHECK (spoilage_units >= 0),
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    closing_stock INTEGER NOT NULL CHECK (closing_stock >= 0),
    stockout_flag INTEGER NOT NULL CHECK (stockout_flag IN (0, 1)),
    lost_sales_units INTEGER NOT NULL CHECK (lost_sales_units >= 0),
    reorder_point INTEGER NOT NULL CHECK (reorder_point >= 0),
    safety_stock INTEGER NOT NULL CHECK (safety_stock >= 0),
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    PRIMARY KEY (store_id, product_id, week_start),
    CHECK (
        (units_received_missing_flag = 1 AND units_received_raw IS NULL AND units_received_clean IS NULL)
        OR
        (units_received_missing_flag = 0 AND units_received_raw IS NOT NULL
         AND units_received_clean = units_received_raw)
    )
);

CREATE TABLE sales (
    order_id TEXT PRIMARY KEY,
    order_date TEXT NOT NULL,
    week_start TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    catalog_unit_price REAL NOT NULL CHECK (catalog_unit_price > 0),
    transaction_unit_price REAL NOT NULL CHECK (transaction_unit_price > 0),
    revenue REAL NOT NULL CHECK (revenue > 0),
    synthetic_flag INTEGER NOT NULL CHECK (synthetic_flag = 1),
    FOREIGN KEY (store_id, product_id, week_start)
        REFERENCES inventory(store_id, product_id, week_start)
);

CREATE INDEX idx_inventory_week ON inventory(week_start);
CREATE INDEX idx_inventory_supplier ON inventory(supplier_id);
CREATE INDEX idx_sales_date ON sales(order_date);
CREATE INDEX idx_sales_week ON sales(store_id, product_id, week_start);
