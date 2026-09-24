"""Validate and clean the original synthetic inventory data without rewriting it."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SOURCE_FILES = ("inventory_ledger.csv", "stores.csv", "products.csv", "suppliers.csv")
INVENTORY_NUMERIC = (
    "opening_stock", "units_received", "spoilage_units", "units_sold",
    "closing_stock", "stockout_flag", "lost_sales_units", "reorder_point",
    "safety_stock",
)
INVENTORY_KEY = ("store_id", "product_id", "week_start")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_raw_inputs() -> None:
    """Copy baseline inputs once; subsequent runs verify rather than overwrite raw files."""
    RAW.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        source, target = DATA / name, RAW / name
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.exists():
            if _digest(source) != _digest(target):
                raise ValueError(f"Raw input differs from baseline: {target}")
        else:
            shutil.copy2(source, target)


def load_raw_data() -> dict[str, pd.DataFrame]:
    ensure_raw_inputs()
    return {name.removesuffix(".csv"): pd.read_csv(RAW / name, dtype="string")
            for name in SOURCE_FILES}


def _numeric(frame: pd.DataFrame, column: str, *, nullable: bool = False,
             integral: bool = True, positive: bool = False) -> pd.Series:
    original = frame[column]
    parsed = pd.to_numeric(original, errors="coerce")
    bad = original.notna() & parsed.isna()
    if bad.any():
        raise ValueError(f"{column}: {int(bad.sum())} nonnumeric values")
    if not nullable and parsed.isna().any():
        raise ValueError(f"{column}: {int(parsed.isna().sum())} missing values")
    if (parsed.dropna() < (1 if positive and integral else 0)).any() or (positive and not integral and (parsed.dropna() <= 0).any()):
        raise ValueError(f"{column}: invalid negative or zero values")
    if integral and (parsed.dropna() % 1 != 0).any():
        raise ValueError(f"{column}: fractional values in integer field")
    return parsed.astype("Int64") if integral else parsed.astype("float64")


def _validate_dimensions(data: dict[str, pd.DataFrame]) -> None:
    for table, key in (("stores", "store_id"), ("products", "product_id"),
                       ("suppliers", "supplier_id")):
        frame = data[table]
        if frame[key].isna().any() or frame[key].duplicated().any():
            raise ValueError(f"{table}: missing or duplicate {key}")
    products, suppliers = data["products"], data["suppliers"]
    for field in ("unit_cost", "unit_price"):
        _numeric(products, field, integral=False, positive=(field == "unit_price"))
    _numeric(suppliers, "avg_lead_time_days")
    reliability = _numeric(suppliers, "reliability_score", integral=False)
    if (reliability > 1).any():
        raise ValueError("reliability_score exceeds 1")
    if (~products["supplier_id"].isin(suppliers["supplier_id"])).any():
        raise ValueError("products contain unknown supplier_id")


def normalize_dates(frame: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(frame["week_start"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError(f"week_start: {int(dates.isna().sum())} invalid dates")
    if (dates.dt.weekday != 0).any():
        raise ValueError("week_start must be a Monday")
    return dates.dt.strftime("%Y-%m-%d")


def validate_relationships(inventory: pd.DataFrame,
                           data: dict[str, pd.DataFrame]) -> dict[str, int]:
    counts = {}
    for field, table in (("store_id", "stores"), ("product_id", "products"),
                         ("supplier_id", "suppliers")):
        counts[f"unmatched_{field}"] = int((~inventory[field].isin(data[table][field])).sum())
    products = data["products"].set_index("product_id")
    expected_supplier = inventory["product_id"].map(products["supplier_id"])
    expected_category = inventory["product_id"].map(products["category"])
    counts["product_supplier_mismatch"] = int((inventory["supplier_id"] != expected_supplier).fillna(True).sum())
    counts["product_category_mismatch"] = int((inventory["category"] != expected_category).fillna(True).sum())
    if any(counts.values()):
        raise ValueError(f"Referential integrity failed: {counts}")
    return counts


def build_clean_inventory(data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    _validate_dimensions(data)
    original = data["inventory_ledger"]
    duplicate_rows = int(original.duplicated().sum())
    inventory = original.drop_duplicates().copy()
    if inventory.duplicated(list(INVENTORY_KEY)).any():
        raise ValueError("Conflicting rows share the inventory composite key")
    inventory["week_start"] = normalize_dates(inventory)

    canonical = {str(value).strip().casefold(): str(value)
                 for value in data["products"]["category"].dropna().unique()}
    category_key = inventory["category"].str.strip().str.casefold()
    inventory["category"] = category_key.map(canonical).astype("string")
    if inventory["category"].isna().any():
        raise ValueError(f"Unmatched category values: {int(inventory['category'].isna().sum())}")

    for field in INVENTORY_NUMERIC:
        inventory[field] = _numeric(inventory, field, nullable=(field == "units_received"))
    if (~inventory["stockout_flag"].isin([0, 1])).any():
        raise ValueError("stockout_flag contains values outside 0/1")
    relationships = validate_relationships(inventory, data)

    inventory = inventory.rename(columns={"units_received": "units_received_raw"})
    inventory.insert(inventory.columns.get_loc("units_received_raw") + 1,
                     "units_received_missing_flag", inventory["units_received_raw"].isna().astype("Int64"))
    inventory.insert(inventory.columns.get_loc("units_received_missing_flag") + 1,
                     "units_received_clean", inventory["units_received_raw"].copy())
    inventory = inventory.sort_values(list(INVENTORY_KEY)).reset_index(drop=True)
    summary = {
        "raw_rows": len(original),
        "raw_duplicate_rows": duplicate_rows,
        "raw_units_received_missing": int(original["units_received"].isna().sum()),
        "clean_rows": len(inventory),
        "clean_duplicate_rows": int(inventory.duplicated().sum()),
        "clean_units_received_missing": int(inventory["units_received_raw"].isna().sum()),
        "raw_category_count": int(original["category"].nunique()),
        "canonical_category_count": int(inventory["category"].nunique()),
        "relationships": relationships,
    }
    return inventory, summary


def validate_inventory_balance(inventory: pd.DataFrame) -> dict[str, int]:
    received = inventory["units_received_raw"]
    rule_a = (inventory["opening_stock"] + received - inventory["spoilage_units"]
              - inventory["units_sold"] == inventory["closing_stock"])
    rule_b = (inventory["opening_stock"] - inventory["spoilage_units"]
              - inventory["units_sold"] == inventory["closing_stock"])
    ordered = inventory.sort_values(list(INVENTORY_KEY)).copy()
    groups = ordered.groupby(["store_id", "product_id"], sort=False)
    previous_close = groups["closing_stock"].shift(1)
    previous_date = pd.to_datetime(groups["week_start"].shift(1))
    current_date = pd.to_datetime(ordered["week_start"])
    transitions = previous_close.notna()
    known = transitions & ordered["units_received_raw"].notna()
    missing = transitions & ordered["units_received_raw"].isna()
    difference = ordered["opening_stock"] - previous_close
    return {
        "rule_a_known_match": int(rule_a.fillna(False).sum()),
        "rule_a_known_rows": int(received.notna().sum()),
        "rule_b_match": int(rule_b.sum()),
        "transition_rows": int(transitions.sum()),
        "transition_seven_day_gaps": int(((current_date - previous_date).dt.days == 7).sum()),
        "transition_known_receipts": int(known.sum()),
        "transition_known_match": int((difference[known] == ordered.loc[known, "units_received_raw"]).sum()),
        "transition_missing_receipts": int(missing.sum()),
        "transition_missing_positive_difference": int((difference[missing] > 0).sum()),
        "transition_missing_zero_difference": int((difference[missing] == 0).sum()),
        "first_rows_missing_receipts": int((~transitions & ordered["units_received_raw"].isna()).sum()),
    }


def validate_stockout_flags(inventory: pd.DataFrame) -> dict[str, int]:
    zero = inventory["closing_stock"] == 0
    flag = inventory["stockout_flag"] == 1
    return {
        "zero_stock_flag_one": int((zero & flag).sum()),
        "zero_stock_flag_zero": int((zero & ~flag).sum()),
        "positive_stock_flag_one": int((~zero & flag).sum()),
        "positive_stock_flag_zero": int((~zero & ~flag).sum()),
    }


def run() -> dict:
    data = load_raw_data()
    inventory, summary = build_clean_inventory(data)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    target = PROCESSED / "inventory_clean.csv"
    temporary = target.with_suffix(".csv.tmp")
    inventory.to_csv(temporary, index=False, date_format="%Y-%m-%d")
    temporary.replace(target)
    summary["balance"] = validate_inventory_balance(inventory)
    summary["stockout"] = validate_stockout_flags(inventory)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
