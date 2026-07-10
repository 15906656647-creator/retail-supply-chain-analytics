"""
Retail Inventory & Supply Chain Analytics
-------------------------------------------
This script:
1. Loads raw weekly inventory ledger + store/product/supplier reference data
2. Cleans it (duplicates, inconsistent text, missing values)
3. Computes core supply chain KPIs: fill rate, stockout rate, inventory
   turnover, days of inventory, spoilage cost, lost sales value
4. Analyzes root causes: stockouts by category/store/region, supplier
   lead-time & reliability vs. stockout rate
5. Builds a simple demand forecast (moving average) vs. actual for one
   product to demonstrate forecasting capability
6. Generates charts
7. Exports a Power-BI-ready clean dataset
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

# ---------- 1. LOAD ----------
ledger = pd.read_csv("data/inventory_ledger.csv", parse_dates=["week_start"])
stores = pd.read_csv("data/stores.csv")
products = pd.read_csv("data/products.csv")
suppliers = pd.read_csv("data/suppliers.csv")
print(f"Raw inventory_ledger rows: {len(ledger)}")

# ---------- 2. CLEAN ----------
before = len(ledger)
ledger = ledger.drop_duplicates()
print(f"Removed {before - len(ledger)} duplicate rows")

ledger["category"] = ledger["category"].str.strip().str.title()
ledger["units_received"] = ledger["units_received"].fillna(0)

ledger.to_csv("data/inventory_ledger_clean.csv", index=False)
print("Saved cleaned data to data/inventory_ledger_clean.csv")

# join reference data
df = (ledger
      .merge(stores, on="store_id", how="left")
      .merge(products, on="product_id", how="left", suffixes=("", "_prod"))
      .merge(suppliers[["supplier_id", "avg_lead_time_days", "reliability_score"]], on="supplier_id", how="left"))
df["category"] = df["category"].fillna(df["category_prod"])

# ---------- 3. CORE KPIs ----------
total_weeks_rows = len(df)
overall_fill_rate = 100 * (1 - df["stockout_flag"].mean())
overall_stockout_rate = 100 * df["stockout_flag"].mean()
df["lost_sales_value"] = df["lost_sales_units"] * df["unit_price"]
total_lost_sales_value = df["lost_sales_value"].sum()

# inventory turnover (approx): annual COGS / avg inventory value, per SKU
# (per store-product first, then averaged within category -- summing COGS
# across many SKUs and dividing by one row's average inventory value would
# badly inflate the ratio, the same pooling trap as the elasticity calc
# in the pricing project)
df["inventory_value"] = df["closing_stock"] * df["unit_cost"]
df["cogs"] = df["units_sold"] * df["unit_cost"]

sku_turnover = df.groupby(["category", "store_id", "product_id"]).apply(
    lambda g: g["cogs"].sum() / g["inventory_value"].mean() if g["inventory_value"].mean() > 0 else np.nan,
    include_groups=False
).rename("turnover").reset_index()

turnover_by_category = sku_turnover.groupby("category")["turnover"].mean().sort_values(ascending=False)
days_of_inventory_by_category = (365 / turnover_by_category).round(1)

print(f"\nOverall fill rate: {overall_fill_rate:.1f}% | Overall stockout rate: {overall_stockout_rate:.1f}%")
print(f"Total estimated lost sales value: {total_lost_sales_value:,.0f}")
print("\n--- Inventory turnover (annualized) by category ---")
print(turnover_by_category.round(2))
print("\n--- Days of inventory outstanding by category ---")
print(days_of_inventory_by_category)

# ---------- 4. ROOT CAUSE: STOCKOUTS ----------
stockout_by_category = df.groupby("category")["stockout_flag"].mean().sort_values(ascending=False) * 100
stockout_by_region = df.groupby("region")["stockout_flag"].mean().sort_values(ascending=False) * 100
stockout_by_store_type = df.groupby("store_type")["stockout_flag"].mean().sort_values(ascending=False) * 100

print("\n--- Stockout rate by category (%) ---")
print(stockout_by_category.round(1))
print("\n--- Stockout rate by region (%) ---")
print(stockout_by_region.round(1))
print("\n--- Stockout rate by store type (%) ---")
print(stockout_by_store_type.round(1))

# supplier performance vs stockouts
supplier_perf = df.groupby("supplier_id").agg(
    avg_lead_time_days=("avg_lead_time_days", "first"),
    reliability_score=("reliability_score", "first"),
    stockout_rate_pct=("stockout_flag", lambda x: 100 * x.mean()),
).round(2).sort_values("stockout_rate_pct", ascending=False)
print("\n--- Supplier performance vs. stockout rate ---")
print(supplier_perf)

lead_time_stockout_corr = supplier_perf["avg_lead_time_days"].corr(supplier_perf["stockout_rate_pct"])
reliability_stockout_corr = supplier_perf["reliability_score"].corr(supplier_perf["stockout_rate_pct"])
print(f"\nCorrelation (lead time vs. stockout rate): {lead_time_stockout_corr:.2f}")
print(f"Correlation (reliability vs. stockout rate): {reliability_stockout_corr:.2f}")

# ---------- 5. SPOILAGE (PERISHABLES) ----------
df["spoilage_cost"] = df["spoilage_units"] * df["unit_cost"]
spoilage_by_category = df.groupby("category")["spoilage_cost"].sum().sort_values(ascending=False)
total_spoilage_cost = df["spoilage_cost"].sum()
print(f"\n--- Total spoilage cost: {total_spoilage_cost:,.0f} ---")
print(spoilage_by_category.round(0))

# ---------- 6. SIMPLE DEMAND FORECAST (moving average) VS ACTUAL ----------
# pick the highest-volume product for a clean illustrative example
top_product_id = df.groupby("product_id")["units_sold"].sum().idxmax()
top_product_name = products.loc[products["product_id"] == top_product_id, "product_name"].iloc[0]
prod_ts = (df[df["product_id"] == top_product_id]
           .groupby("week_start")["units_sold"].sum()
           .sort_index())

window = 4
forecast = prod_ts.rolling(window=window).mean().shift(1)  # forecast using prior 4 weeks, no lookahead
valid = pd.DataFrame({"actual": prod_ts, "forecast": forecast}).dropna()
mape = (np.abs(valid["actual"] - valid["forecast"]) / valid["actual"].replace(0, np.nan)).mean() * 100
print(f"\n--- Demand forecast (4-week moving average) for '{top_product_name}' ---")
print(f"MAPE: {mape:.1f}%")

# ---------- 7. CHARTS ----------
plt.style.use("seaborn-v0_8-whitegrid")

# 7a. Stockout rate by category
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(stockout_by_category.index, stockout_by_category.values, color="#C73E1D")
ax.set_title("Stockout Rate by Category (%)", fontsize=14, fontweight="bold")
ax.set_xlabel("Stockout Rate (%)")
plt.tight_layout()
plt.savefig("images/stockout_rate_by_category.png", dpi=150)
plt.close()

# 7b. Stockout rate by region
fig, ax = plt.subplots(figsize=(7, 5))
ax.bar(stockout_by_region.index, stockout_by_region.values, color="#2E86AB")
ax.set_title("Stockout Rate by Region (%)", fontsize=14, fontweight="bold")
ax.set_ylabel("Stockout Rate (%)")
plt.tight_layout()
plt.savefig("images/stockout_rate_by_region.png", dpi=150)
plt.close()

# 7c. Inventory turnover by category
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(turnover_by_category.index, turnover_by_category.values, color="#F18F01")
ax.set_title("Inventory Turnover by Category (annualized)", fontsize=14, fontweight="bold")
ax.set_xlabel("Turnover Ratio (COGS / Avg Inventory Value)")
plt.tight_layout()
plt.savefig("images/inventory_turnover_by_category.png", dpi=150)
plt.close()

# 7d. Supplier lead time vs stockout rate scatter
fig, ax = plt.subplots(figsize=(7, 5))
ax.scatter(supplier_perf["avg_lead_time_days"], supplier_perf["stockout_rate_pct"],
           s=100, color="#A23B72")
for sid, row in supplier_perf.iterrows():
    ax.annotate(sid, (row["avg_lead_time_days"], row["stockout_rate_pct"]),
                fontsize=8, xytext=(4, 4), textcoords="offset points")
ax.set_title("Supplier Lead Time vs. Stockout Rate", fontsize=14, fontweight="bold")
ax.set_xlabel("Avg Lead Time (days)")
ax.set_ylabel("Stockout Rate (%)")
plt.tight_layout()
plt.savefig("images/supplier_lead_time_vs_stockouts.png", dpi=150)
plt.close()

# 7e. Demand forecast vs actual
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(valid.index, valid["actual"], label="Actual", color="#2E86AB", marker="o", markersize=3)
ax.plot(valid.index, valid["forecast"], label="Forecast (4-wk moving avg)", color="#C73E1D", linestyle="--")
ax.set_title(f"Demand Forecast vs. Actual — {top_product_name}", fontsize=14, fontweight="bold")
ax.set_ylabel("Units Sold (weekly)")
plt.xticks(rotation=45, ha="right")
ax.legend()
plt.tight_layout()
plt.savefig("images/demand_forecast_vs_actual.png", dpi=150)
plt.close()

# 7f. Spoilage cost by category
fig, ax = plt.subplots(figsize=(7, 5))
ax.bar(spoilage_by_category.index, spoilage_by_category.values, color="#5B8C5A")
ax.set_title("Total Spoilage Cost by Category", fontsize=14, fontweight="bold")
ax.set_ylabel("Spoilage Cost")
plt.xticks(rotation=20, ha="right")
plt.tight_layout()
plt.savefig("images/spoilage_cost_by_category.png", dpi=150)
plt.close()

print("\nCharts saved to images/")

# ---------- 8. SAVE SUMMARY ----------
summary = {
    "overall_fill_rate_pct": round(overall_fill_rate, 1),
    "overall_stockout_rate_pct": round(overall_stockout_rate, 1),
    "total_lost_sales_value": round(total_lost_sales_value, 0),
    "total_spoilage_cost": round(total_spoilage_cost, 0),
    "worst_stockout_category": stockout_by_category.idxmax(),
    "worst_stockout_category_rate_pct": round(stockout_by_category.max(), 1),
    "worst_stockout_region": stockout_by_region.idxmax(),
    "lead_time_stockout_corr": round(lead_time_stockout_corr, 2),
    "reliability_stockout_corr": round(reliability_stockout_corr, 2),
    "demand_forecast_example_product": top_product_name,
    "demand_forecast_mape_pct": round(mape, 1),
}
pd.Series(summary).to_csv("data/summary_metrics.csv")
print("\nSummary:", summary)

# ---------- 9. POWER-BI-READY EXPORT ----------
# a single flat, joined table is the easiest starting point for a Power BI model
powerbi_export = df[[
    "store_id", "store_name", "region", "store_type",
    "product_id", "product_name", "category",
    "week_start", "opening_stock", "units_received", "spoilage_units",
    "units_sold", "closing_stock", "stockout_flag", "lost_sales_units",
    "lost_sales_value", "reorder_point", "safety_stock",
    "supplier_id", "avg_lead_time_days", "reliability_score",
    "unit_cost", "unit_price", "inventory_value", "cogs", "spoilage_cost",
]]
powerbi_export.to_csv("data/powerbi_dataset.csv", index=False)
print("Saved Power BI-ready flat dataset to data/powerbi_dataset.csv")
