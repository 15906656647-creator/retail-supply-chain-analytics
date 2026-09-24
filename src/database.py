"""Rebuild the Phase 1 SQLite database, execute SQL, and report validation."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from . import data_cleaning, synthetic_sales


ROOT = data_cleaning.ROOT
DATABASE = ROOT / "data" / "database" / "business_analytics.db"
REPORT = ROOT / "reports" / "DATA_QUALITY_REPORT.md"
TABLES = ("stores", "suppliers", "products", "inventory", "sales")


def _rows(frame: pd.DataFrame):
    for row in frame.itertuples(index=False, name=None):
        yield tuple(None if pd.isna(value) else value.item() if hasattr(value, "item") else value
                    for value in row)


def _insert_frame(connection: sqlite3.Connection, table: str, frame: pd.DataFrame) -> None:
    columns = list(frame.columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    connection.executemany(sql, _rows(frame))


def execute_business_queries(connection: sqlite3.Connection) -> dict[str, int]:
    source = (ROOT / "sql" / "business_analysis.sql").read_text(encoding="utf-8")
    markers = list(re.finditer(r"(?m)^-- Q(\d{2}) ([^\n]+)\n", source))
    if [int(match.group(1)) for match in markers] != list(range(1, 19)):
        raise ValueError("business_analysis.sql must contain Q01–Q18 in order")
    result = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(source)
        statement = source[marker.end():end].strip()
        if not statement or not statement.rstrip().endswith(";"):
            raise ValueError(f"Query Q{index + 1:02d} is incomplete")
        rows = connection.execute(statement).fetchall()
        # Empty threshold lists are valid outcomes; all other queries must return rows.
        if not rows and index + 1 not in (10, 11):
            raise ValueError(f"Query Q{index + 1:02d} returned no rows")
        result[f"Q{index + 1:02d} {marker.group(2)}"] = len(rows)
    return result


def reconcile_sql_pandas(connection: sqlite3.Connection, inventory: pd.DataFrame,
                         sales: pd.DataFrame) -> dict[str, dict[str, int]]:
    expected = {
        "inventory_rows": len(inventory),
        "sales_rows": len(sales),
        "inventory_units_sold": int(inventory["units_sold"].sum()),
        "synthetic_sales_quantity": int(sales["quantity"].sum()),
        "synthetic_revenue_cents": int(sales["revenue"].map(synthetic_sales._cents).sum()),
        "synthetic_orders": int(sales["order_id"].nunique()),
    }
    actual = {
        "inventory_rows": connection.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
        "sales_rows": connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
        "inventory_units_sold": connection.execute("SELECT SUM(units_sold) FROM inventory").fetchone()[0],
        "synthetic_sales_quantity": connection.execute("SELECT SUM(quantity) FROM sales").fetchone()[0],
        "synthetic_revenue_cents": connection.execute(
            "SELECT SUM(CAST(ROUND(revenue * 100) AS INTEGER)) FROM sales"
        ).fetchone()[0],
        "synthetic_orders": connection.execute("SELECT COUNT(DISTINCT order_id) FROM sales").fetchone()[0],
    }
    if expected != actual or expected["inventory_units_sold"] != expected["synthetic_sales_quantity"]:
        raise ValueError(f"SQL/Pandas reconciliation failed: pandas={expected}, sql={actual}")
    return {key: {"pandas": value, "sql": actual[key]} for key, value in expected.items()}


def _quality_report(raw: dict[str, pd.DataFrame], inventory: pd.DataFrame,
                    sales: pd.DataFrame, cleaning: dict, generation: dict,
                    counts: dict[str, int], queries: dict[str, int],
                    reconciliation: dict[str, dict[str, int]]) -> str:
    balance, stockout = cleaning["balance"], cleaning["stockout"]
    source = raw["inventory_ledger"]
    products = raw["products"]
    canonical = {str(value).strip().casefold(): str(value)
                 for value in products["category"].dropna().unique()}
    lines = [
        "# Phase 1 Data Quality Report", "",
        "本报告由 `python -m src.database` 基于当前文件和实际 SQLite 查询生成。全部数据为 synthetic data。", "",
        "## 1. Dataset Overview", "",
        "| Dataset | Rows | Columns | Role | Primary key candidate |", "|---|---:|---:|---|---|",
        f"| raw inventory_ledger | {len(source)} | {len(source.columns)} | 原始周度库存事实 | store_id + product_id + week_start（含重复） |",
        f"| processed inventory_clean | {len(inventory)} | {len(inventory.columns)} | 清洗库存事实 | store_id + product_id + week_start |",
        f"| raw/processed sales | {len(sales)} | {len(sales.columns)} | 合成单商品订单事实 | order_id |",
        f"| stores | {len(raw['stores'])} | {len(raw['stores'].columns)} | 门店维表 | store_id |",
        f"| products | {len(products)} | {len(products.columns)} | 商品维表 | product_id |",
        f"| suppliers | {len(raw['suppliers'])} | {len(raw['suppliers'].columns)} | 供应商维表 | supplier_id |",
        "", "## 2. Duplicate Records", "",
        f"原始库存整行重复 {cleaning['raw_duplicate_rows']} 条；清洗后重复 {cleaning['clean_duplicate_rows']} 条。仅删除整行完全相同的记录；同复合键但内容不同会报错。",
        "", "## 3. Missing Values and Numeric Validation", "",
        f"原始 `units_received` 缺失 {cleaning['raw_units_received_missing']} 个；去重后缺失 {cleaning['clean_units_received_missing']} 个。",
        "清洗层保留 `units_received_raw`、`units_received_missing_flag`、`units_received_clean`；缺失 clean 值保持 NULL。NULL 不代表零收货。",
        "已检查库存数值字段的非数字、缺失、负值、非整数、非法 stockout flag，以及无效或非周一日期；除允许的收货量缺失外，当前数据均通过。极端值只做统计标记，不据主观阈值删除。", "",
        "| Numeric field | Min | Max | IQR statistical outliers |", "|---|---:|---:|---:|",
    ]
    for field in data_cleaning.INVENTORY_NUMERIC:
        series = pd.to_numeric(source[field], errors="coerce").dropna()
        q1, q3 = series.quantile([0.25, 0.75])
        span = q3 - q1
        flagged = int(((series < q1 - 1.5 * span) | (series > q3 + 1.5 * span)).sum())
        lines.append(f"| {field} | {series.min():g} | {series.max():g} | {flagged} |")
    lines.extend(["", "## 4. Category Standardization", "",
                  f"原始 {cleaning['raw_category_count']} 种写法，规范化后 {cleaning['canonical_category_count']} 类；去空格、大小写归一，再映射到产品表的类别。未匹配类别 0。", "",
                  "| Raw value | Canonical value | Rows |", "|---|---|---:|"])
    for value, count in source["category"].value_counts().sort_index().items():
        lines.append(f"| `{value}` | {canonical[str(value).strip().casefold()]} | {count} |")
    lines.extend(["", "## 5. Referential Integrity", "",
                  "| Check | Unmatched rows |", "|---|---:|"])
    for key, value in cleaning["relationships"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## 6. Inventory Accounting Validation", "",
                  f"Rule A（当周 opening + received − spoilage − sold = closing）：已知收货量的 {balance['rule_a_known_rows']} 行中匹配 {balance['rule_a_known_match']} 行；另有 {cleaning['clean_units_received_missing']} 行收货量未知，不参与该规则判断。",
                  f"Rule B（当周 opening − spoilage − sold = closing）：{balance['rule_b_match']} / {len(inventory)} 行匹配。",
                  f"跨周：{balance['transition_rows']} 个同门店商品连续周配对，全部间隔七天。已知本周收货量 {balance['transition_known_receipts']} 个配对，其中 {balance['transition_known_match']} 个满足本周 opening − 上周 closing = 本周 received。",
                  f"另有 {balance['transition_missing_receipts']} 个配对的收货量缺失；其中差额为正 {balance['transition_missing_positive_difference']} 个、为零 {balance['transition_missing_zero_difference']} 个。首周缺失 {balance['first_rows_missing_receipts']} 个，没有上周可比较。",
                  "这些等式强烈支持收货量已反映在本周期初库存，但仓库没有生成逻辑或权威字段定义。**inventory accounting semantics: UNRESOLVED**。原始库存值没有被改写，下游 SQL 不把 Rule A 当作已验证规则。",
                  "", "## 7. Stockout Flag Validation", "",
                  "| Condition | Rows |", "|---|---:|",
                  f"| closing_stock = 0, stockout_flag = 1 | {stockout['zero_stock_flag_one']} |",
                  f"| closing_stock = 0, stockout_flag = 0 | {stockout['zero_stock_flag_zero']} |",
                  f"| closing_stock > 0, stockout_flag = 1 | {stockout['positive_stock_flag_one']} |",
                  f"| closing_stock > 0, stockout_flag = 0 | {stockout['positive_stock_flag_zero']} |",
                  "保留原始 `stockout_flag`；未以零库存值覆盖。", "",
                  "## 8. Synthetic Sales Generation", "",
                  f"固定随机种子 {generation['random_seed']}；按排序后的每个门店/商品/库存周把 `units_sold` 拆成数量 1–10 的单商品订单行，零销量不生成订单。订单数与销售行数均为 {generation['orders']}。",
                  f"订单日期范围 {generation['date_min']} 至 {generation['date_max']}，均落在对应七天库存周内。末周延伸至 2026-01-04，因此 2026 年 1 月只有部分月份。",
                  "商品目录价格来自 `products.unit_price`；成交价通过种子控制的 0–5% 折扣生成并按分四舍五入，逐行 Revenue = quantity × transaction_unit_price。所有订单、成交价和 Revenue 均为 synthetic。",
                  f"匹配组合 {generation['matched_combinations']}，未匹配组合 {generation['unmatched_combinations']}；最大数量差 {generation['maximum_quantity_difference']}，总差 {generation['total_quantity_difference']}。库存总销量与合成销售量均为 {generation['inventory_units_sold']}；合成收入 {generation['revenue_cents'] / 100:,.2f}。", "",
                  "## 9. SQLite and SQL Validation", "",
                  f"数据库：`data/database/business_analytics.db`。`PRAGMA foreign_keys=ON`，`foreign_key_check` 无违规，`integrity_check` 为 `ok`。", "",
                  "| Table | Rows |", "|---|---:|"])
    for table, count in counts.items():
        lines.append(f"| {table} | {count} |")
    lines.extend(["", "全部 18 项 `sql/business_analysis.sql` 查询已在 SQLite 中执行；低于阈值的清单允许合法空结果。", "",
                  "| Query | Result rows |", "|---|---:|"])
    for name, count in queries.items():
        lines.append(f"| {name} | {count} |")
    lines.extend(["", "### SQL / Pandas Reconciliation", "",
                  "| Metric | Pandas | SQLite |", "|---|---:|---:|"])
    for metric, values in reconciliation.items():
        lines.append(f"| {metric} | {values['pandas']} | {values['sql']} |")
    lines.extend(["", "所有核对均 PASS；收入以整数分核对。", "",
                  "## 10. Data Limitations", "",
                  "- 全部数据为 synthetic，没有真实企业交易；订单并非从原库存台账恢复的真实订单。每行是单商品订单，不代表购物篮。",
                  "- 成交价及折扣为生成值，无真实折扣、退款或促销历史；2025 年 1 月和 2026 年 1 月为部分月份，月环比不可直接解读为完整月份趋势。",
                  "- `reliability_score` 是供应商维表中的静态属性，没有逐笔采购与履约记录。",
                  "- 收货量/期初库存的生成语义仍未获权威定义；缺失收货量保留 NULL，stockout 标记与零库存存在差异。",
                  "- IQR 仅标记统计极值，不代表已确认的业务异常。", ""])
    return "\n".join(lines)


def run() -> dict:
    raw = data_cleaning.load_raw_data()
    inventory, cleaning = data_cleaning.build_clean_inventory(raw)
    inventory_path = data_cleaning.PROCESSED / "inventory_clean.csv"
    if (not inventory_path.is_file() or
            inventory_path.read_bytes().replace(b"\r\n", b"\n") !=
            inventory.to_csv(index=False).encode("utf-8").replace(b"\r\n", b"\n")):
        raise ValueError("Processed inventory differs from the reproducible cleaning output")
    cleaning["balance"] = data_cleaning.validate_inventory_balance(inventory)
    cleaning["stockout"] = data_cleaning.validate_stockout_flags(inventory)
    sales_path = data_cleaning.PROCESSED / "sales_clean.csv"
    raw_sales_path = data_cleaning.RAW / "sales.csv"
    if not sales_path.is_file() or not raw_sales_path.is_file():
        raise FileNotFoundError("Run python -m src.synthetic_sales first")
    expected_sales = synthetic_sales.generate_sales(inventory, raw["products"])
    if (sales_path.read_bytes().replace(b"\r\n", b"\n") != expected_sales or
            raw_sales_path.read_bytes().replace(b"\r\n", b"\n") != expected_sales):
        raise ValueError("Sales data differ from the deterministic generator")
    sales = pd.read_csv(sales_path)
    generation = synthetic_sales.validate_sales(sales, inventory, pd.read_csv(data_cleaning.RAW / "products.csv"))

    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATABASE.with_suffix(".db.tmp")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        with connection:
            for table in ("stores", "suppliers", "products"):
                _insert_frame(connection, table, raw[table])
            _insert_frame(connection, "inventory", inventory)
            _insert_frame(connection, "sales", sales)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if violations or integrity != "ok":
            raise ValueError(f"SQLite integrity failure: foreign_keys={violations[:5]}, integrity={integrity}")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in TABLES}
        expected_counts = {"stores": len(raw["stores"]), "suppliers": len(raw["suppliers"]),
                           "products": len(raw["products"]), "inventory": len(inventory),
                           "sales": len(sales)}
        if counts != expected_counts:
            raise ValueError(f"SQLite row counts mismatch: {counts} != {expected_counts}")
        queries = execute_business_queries(connection)
        reconciliation = reconcile_sql_pandas(connection, inventory, sales)
        report_text = _quality_report(raw, inventory, sales, cleaning, generation,
                                      counts, queries, reconciliation)
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    temporary.replace(DATABASE)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_tmp = REPORT.with_suffix(".md.tmp")
    report_tmp.write_text(report_text, encoding="utf-8")
    report_tmp.replace(REPORT)
    return {"database": str(DATABASE), "tables": counts, "foreign_key_violations": 0,
            "queries_executed": queries, "reconciliation": reconciliation,
            "report": str(REPORT)}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
