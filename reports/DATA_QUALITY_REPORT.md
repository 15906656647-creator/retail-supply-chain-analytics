# Phase 1 Data Quality Report

本报告由 `python -m src.database` 基于当前文件和实际 SQLite 查询生成。全部数据为 synthetic data。

## 1. Dataset Overview

| Dataset | Rows | Columns | Role | Primary key candidate |
|---|---:|---:|---|---|
| raw inventory_ledger | 17417 | 14 | 原始周度库存事实 | store_id + product_id + week_start（含重复） |
| processed inventory_clean | 17160 | 16 | 清洗库存事实 | store_id + product_id + week_start |
| raw/processed sales | 149949 | 10 | 合成单商品订单事实 | order_id |
| stores | 16 | 4 | 门店维表 | store_id |
| products | 30 | 6 | 商品维表 | product_id |
| suppliers | 10 | 5 | 供应商维表 | supplier_id |

## 2. Duplicate Records

原始库存整行重复 257 条；清洗后重复 0 条。仅删除整行完全相同的记录；同复合键但内容不同会报错。

## 3. Missing Values and Numeric Validation

原始 `units_received` 缺失 519 个；去重后缺失 515 个。
清洗层保留 `units_received_raw`、`units_received_missing_flag`、`units_received_clean`；缺失 clean 值保持 NULL。NULL 不代表零收货。
已检查库存数值字段的非数字、缺失、负值、非整数、非法 stockout flag，以及无效或非周一日期；除允许的收货量缺失外，当前数据均通过。极端值只做统计标记，不据主观阈值删除。

| Numeric field | Min | Max | IQR statistical outliers |
|---|---:|---:|---:|
| opening_stock | 0 | 1747 | 875 |
| units_received | 0 | 1008 | 2008 |
| spoilage_units | 0 | 87 | 2506 |
| units_sold | 0 | 174 | 383 |
| closing_stock | 0 | 1568 | 930 |
| stockout_flag | 0 | 1 | 309 |
| lost_sales_units | 0 | 89 | 297 |
| reorder_point | 21 | 291 | 314 |
| safety_stock | 4 | 40 | 0 |

## 4. Category Standardization

原始 15 种写法，规范化后 5 类；去空格、大小写归一，再映射到产品表的类别。未匹配类别 0。

| Raw value | Canonical value | Rows |
|---|---|---:|
| ` Beverages ` | Beverages | 271 |
| ` Household Essentials ` | Household Essentials | 260 |
| ` Packaged Foods ` | Packaged Foods | 264 |
| ` Perishables ` | Perishables | 280 |
| ` Personal Care ` | Personal Care | 310 |
| `Beverages` | Beverages | 2787 |
| `Household Essentials` | Household Essentials | 2809 |
| `Packaged Foods` | Packaged Foods | 2801 |
| `Perishables` | Perishables | 2821 |
| `Personal Care` | Personal Care | 2777 |
| `beverages` | Beverages | 425 |
| `household essentials` | Household Essentials | 413 |
| `packaged foods` | Packaged Foods | 410 |
| `perishables` | Perishables | 387 |
| `personal care` | Personal Care | 402 |

## 5. Referential Integrity

| Check | Unmatched rows |
|---|---:|
| unmatched_store_id | 0 |
| unmatched_product_id | 0 |
| unmatched_supplier_id | 0 |
| product_supplier_mismatch | 0 |
| product_category_mismatch | 0 |

## 6. Inventory Accounting Validation

Rule A（当周 opening + received − spoilage − sold = closing）：已知收货量的 16645 行中匹配 11741 行；另有 515 行收货量未知，不参与该规则判断。
Rule B（当周 opening − spoilage − sold = closing）：17160 / 17160 行匹配。
跨周：16830 个同门店商品连续周配对，全部间隔七天。已知本周收货量 16326 个配对，其中 16326 个满足本周 opening − 上周 closing = 本周 received。
另有 504 个配对的收货量缺失；其中差额为正 132 个、为零 372 个。首周缺失 11 个，没有上周可比较。
这些等式强烈支持收货量已反映在本周期初库存，但仓库没有生成逻辑或权威字段定义。**inventory accounting semantics: UNRESOLVED**。原始库存值没有被改写，下游 SQL 不把 Rule A 当作已验证规则。

## 7. Stockout Flag Validation

| Condition | Rows |
|---|---:|
| closing_stock = 0, stockout_flag = 1 | 303 |
| closing_stock = 0, stockout_flag = 0 | 9 |
| closing_stock > 0, stockout_flag = 1 | 0 |
| closing_stock > 0, stockout_flag = 0 | 16848 |
保留原始 `stockout_flag`；未以零库存值覆盖。

## 8. Synthetic Sales Generation

固定随机种子 42；按排序后的每个门店/商品/库存周把 `units_sold` 拆成数量 1–10 的单商品订单行，零销量不生成订单。订单数与销售行数均为 149949。
订单日期范围 2025-01-06 至 2026-01-04，均落在对应七天库存周内。末周延伸至 2026-01-04，因此 2026 年 1 月只有部分月份。
商品目录价格来自 `products.unit_price`；成交价通过种子控制的 0–5% 折扣生成并按分四舍五入，逐行 Revenue = quantity × transaction_unit_price。所有订单、成交价和 Revenue 均为 synthetic。
匹配组合 17160，未匹配组合 0；最大数量差 0，总差 0。库存总销量与合成销售量均为 705399；合成收入 336,627,819.99。

## 9. SQLite and SQL Validation

数据库：`data/database/business_analytics.db`。`PRAGMA foreign_keys=ON`，`foreign_key_check` 无违规，`integrity_check` 为 `ok`。

| Table | Rows |
|---|---:|
| stores | 16 |
| suppliers | 10 |
| products | 30 |
| inventory | 17160 |
| sales | 149949 |

全部 18 项 `sql/business_analysis.sql` 查询已在 SQLite 中执行；低于阈值的清单允许合法空结果。

| Query | Result rows |
|---|---:|
| Q01 Monthly Revenue (synthetic transactions) | 13 |
| Q02 Monthly Orders (one synthetic single-item order per row) | 13 |
| Q03 Monthly Units Sold (synthetic transactions) | 13 |
| Q04 Product Sales Ranking (synthetic transactions) | 30 |
| Q05 Category Sales Ranking (synthetic transactions) | 5 |
| Q06 Region Sales Ranking (synthetic transactions) | 4 |
| Q07 Monthly Revenue Growth (synthetic; complete calendar months only) | 13 |
| Q08 Latest Inventory Level per store/product | 330 |
| Q09 Stockout Rate by weekly inventory record | 1 |
| Q10 Latest stock below reorder point | 87 |
| Q11 Latest stock below safety stock | 10 |
| Q12 Inventory by Region from latest store/product snapshots | 4 |
| Q13 Inventory by Category from latest store/product snapshots | 5 |
| Q14 Monthly Units Sold from weekly inventory (grouped by week_start month) | 12 |
| Q15 Supplier Product Count | 10 |
| Q16 Supplier Average Lead Time (static master-data attribute) | 10 |
| Q17 Supplier Reliability Score (static master-data attribute, not delivery history) | 10 |
| Q18 Stockout Rate by Supplier from weekly inventory | 10 |

### SQL / Pandas Reconciliation

| Metric | Pandas | SQLite |
|---|---:|---:|
| inventory_rows | 17160 | 17160 |
| sales_rows | 149949 | 149949 |
| inventory_units_sold | 705399 | 705399 |
| synthetic_sales_quantity | 705399 | 705399 |
| synthetic_revenue_cents | 33662781999 | 33662781999 |
| synthetic_orders | 149949 | 149949 |

所有核对均 PASS；收入以整数分核对。

## 10. Data Limitations

- 全部数据为 synthetic，没有真实企业交易；订单并非从原库存台账恢复的真实订单。每行是单商品订单，不代表购物篮。
- 成交价及折扣为生成值，无真实折扣、退款或促销历史；2025 年 1 月和 2026 年 1 月为部分月份，月环比不可直接解读为完整月份趋势。
- `reliability_score` 是供应商维表中的静态属性，没有逐笔采购与履约记录。
- 收货量/期初库存的生成语义仍未获权威定义；缺失收货量保留 NULL，stockout 标记与零库存存在差异。
- IQR 仅标记统计极值，不代表已确认的业务异常。
