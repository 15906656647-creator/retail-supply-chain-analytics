# 企业经营数据智能分析与 AI 应用场景评估项目总纲

## 1. 项目定位

本项目是一个基于公开 synthetic retail data 的企业经营数据分析与 AI 场景验证项目。

核心目标不是构建大型生产系统，而是完整展示以下企业数据工作链路：

```text
业务问题
→ 数据理解
→ 数据清洗
→ 数据库建设
→ SQL 分析
→ KPI 指标体系
→ 多维经营分析
→ AI 场景验证
→ 库存风险预警
→ Power BI 可视化
→ 报告输出
```

---

# 2. 项目背景

企业经营分析通常涉及销售、库存、采购、产品、区域和供应商等多类数据。

如果这些数据分散在不同业务表中，企业分析人员通常需要完成：

- 数据抽取
- 数据清洗
- 字段标准化
- 多表关联
- 指标统一
- 趋势分析
- 异常识别
- 可视化展示

在完成基础经营分析之后，还可以进一步验证 AI 应用场景，例如：

- 销售预测
- 需求预测
- 缺货预警
- 库存异常预警

本项目使用一个公开零售库存分析项目作为基础，逐步扩展上述能力。

---

# 3. 原始项目

原项目：

**Retail Inventory & Supply Chain Analytics**

GitHub：

https://github.com/DataWithSoumya/retail-supply-chain-analytics

原项目技术：

```text
Python
Pandas
NumPy
Matplotlib
SQL
Power BI
```

原项目已经包含：

- 库存数据
- 门店数据
- 产品数据
- 供应商数据
- 数据清洗
- 库存 KPI
- 供应商分析
- 简单需求预测
- Power BI 数据集
- Power BI 搭建指南

本项目将在此基础上进行二次开发。

---

# 4. 项目核心业务问题

本项目围绕以下业务问题展开。

## 4.1 销售

需要回答：

- 企业销售额如何变化？
- 订单量如何变化？
- 哪些产品贡献最高？
- 哪些品类增长最快？
- 不同区域表现如何？
- 是否存在明显的月度变化？

---

## 4.2 库存

需要回答：

- 当前库存水平如何？
- 哪些产品存在缺货？
- 哪些商品库存周转较慢？
- 哪些商品可能存在过量库存？
- 库存风险主要集中在哪些品类或门店？

---

## 4.3 供应商

需要回答：

- 哪些供应商交付稳定？
- 哪些供应商与缺货风险关联更明显？
- 供应商 lead time 如何？
- supplier reliability 是否存在明显差异？

---

## 4.4 AI 场景

需要回答：

- 历史销售是否具有可预测性？
- 简单模型是否优于 naive baseline？
- MAE / RMSE 表现如何？
- 预测结果是否可以辅助库存风险识别？

---

# 5. 系统总体架构

```text
┌──────────────────────────────┐
│       Raw Synthetic Data     │
│ sales / inventory / product  │
│ stores / suppliers           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│        Data Cleaning         │
│ Python + Pandas              │
│ Missing / Duplicate / Type   │
│ Standardization / Validation │
└──────────────┬───────────────┘
               │
               ├────────────────────────┐
               ▼                        ▼
┌──────────────────────┐   ┌──────────────────────┐
│       SQLite         │   │ Processed CSV Layer  │
│ Business Tables      │   │ Analytics Dataset    │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────┐
│     SQL Analysis     │   │  Python KPI Analysis │
│ Revenue / Inventory │   │ Multi-dimensional    │
└──────────┬───────────┘   └──────────┬───────────┘
           │                          │
           └────────────┬─────────────┘
                        ▼
             ┌──────────────────────┐
             │ Forecasting Module   │
             │ Baseline / LR / RF   │
             │ MAE / RMSE           │
             └──────────┬───────────┘
                        ▼
             ┌──────────────────────┐
             │ Inventory Alerts     │
             │ Normal / Low / Risk  │
             │ / Overstock          │
             └──────────┬───────────┘
                        ▼
             ┌──────────────────────┐
             │ Power BI Dataset     │
             │ Dashboard & Reports  │
             └──────────────────────┘
```

---

# 6. 数据模型

## 6.1 Stores

建议字段：

```text
store_id
store_name
region
store_type
```

---

## 6.2 Products

建议字段：

```text
product_id
product_name
category
supplier_id
unit_cost
unit_price
```

---

## 6.3 Suppliers

建议字段：

```text
supplier_id
supplier_name
lead_time_days
reliability_score
```

---

## 6.4 Sales

建议字段：

```text
order_id
order_date
store_id
product_id
quantity
unit_price
revenue
```

---

## 6.5 Inventory

建议字段：

```text
date
store_id
product_id
opening_stock
units_received
units_sold
closing_stock
reorder_point
stockout_flag
```

---

# 7. KPI 指标体系

## 销售类

### Revenue

```text
Revenue = SUM(quantity × unit_price)
```

### Orders

```text
Orders = COUNT(DISTINCT order_id)
```

### Units Sold

```text
Units Sold = SUM(quantity)
```

### Average Order Value

```text
AOV = Revenue / Orders
```

### MoM Growth

```text
MoM Growth =
(Current Month Revenue - Previous Month Revenue)
/
Previous Month Revenue
```

---

## 库存类

### Stockout Rate

```text
Stockout Rate =
Stockout Records
/
Total Inventory Records
```

### Fill Rate

```text
Fill Rate = 1 - Stockout Rate
```

### Inventory Turnover

根据数据条件选择合理定义，并在文档中明确计算口径。

---

## 供应商类

建议指标：

```text
Average Lead Time
Supplier Reliability
Stockout Rate by Supplier
Units Received
Delivery Performance
```

---

# 8. AI 模块设计

## 8.1 任务定义

预测未来销售 / 需求量。

目标变量：

```text
demand
```

或：

```text
units_sold
```

---

## 8.2 特征

时间特征：

```text
month
week_of_year
day_of_week
```

滞后特征：

```text
lag_1
lag_7
```

滚动特征：

```text
rolling_mean_7
rolling_mean_30
```

---

## 8.3 模型

### Baseline

Naive Forecast

### Model 1

Linear Regression

### Model 2

Random Forest Regressor

---

## 8.4 数据划分

必须按照时间顺序划分：

```text
Historical Data
├── Train
└── Test
```

禁止随机 shuffle 导致未来数据进入训练集。

---

## 8.5 评价指标

### MAE

Mean Absolute Error

特点：

- 易解释
- 与原始预测单位一致

### RMSE

Root Mean Squared Error

特点：

- 对较大误差更加敏感
- 可以反映极端预测偏差

---

# 9. 库存风险模型

预测模型并不直接等于业务价值。

因此，本项目进一步构建库存预警逻辑。

输入：

```text
current_stock
forecast_demand
safety_stock
reorder_point
```

输出：

```text
NORMAL
LOW_STOCK
STOCKOUT_RISK
OVERSTOCK
```

同时生成：

```text
risk_reason
```

例如：

```text
Forecast demand exceeds available stock
```

使结果具有可解释性。

---

# 10. Power BI 设计

## Page 1：Executive Overview

核心卡片：

```text
Revenue
Orders
Units Sold
MoM Growth
Stockout Rate
```

图表：

- Revenue Trend
- Sales by Region
- Sales by Category

---

## Page 2：Sales Performance

图表：

- Product Ranking
- Category Ranking
- Regional Comparison
- Monthly Growth

---

## Page 3：Inventory Health

图表：

- Current Inventory
- Stockout Rate
- Inventory Turnover
- Risk Status Distribution

---

## Page 4：Supplier Performance

图表：

- Supplier Reliability
- Lead Time
- Stockout Rate
- Delivery Volume

---

## Page 5：Forecast & Alerts

图表：

- Actual vs Forecast
- Forecast Error
- Low Stock Items
- Stockout Risk Items

---

# 11. 推荐项目目录

最终目标：

```text
retail-supply-chain-analytics/
│
├── data/
│   ├── raw/
│   │   ├── inventory_ledger.csv
│   │   ├── stores.csv
│   │   ├── products.csv
│   │   ├── suppliers.csv
│   │   └── sales.csv
│   │
│   ├── processed/
│   │   ├── clean_business_data.csv
│   │   ├── monthly_kpi.csv
│   │   ├── product_kpi.csv
│   │   ├── region_kpi.csv
│   │   ├── forecast_results.csv
│   │   ├── inventory_alerts.csv
│   │   └── powerbi_business_dataset.csv
│   │
│   └── database/
│       └── business_analytics.db
│
├── src/
│   ├── data_cleaning.py
│   ├── database.py
│   ├── kpi_analysis.py
│   ├── forecasting.py
│   └── inventory_alerts.py
│
├── sql/
│   ├── schema.sql
│   └── business_analysis.sql
│
├── reports/
│   ├── DATA_QUALITY_REPORT.md
│   ├── MODEL_EVALUATION.md
│   └── BUSINESS_INSIGHTS.md
│
├── images/
│
├── powerbi/
│   └── POWER_BI_GUIDE.md
│
├── tests/
│   ├── test_data_cleaning.py
│   ├── test_kpi_analysis.py
│   ├── test_forecasting.py
│   └── test_inventory_alerts.py
│
├── PROJECT_INTRODUCTION.md
├── PROJECT_MASTER_PLAN.md
├── PHASED_IMPLEMENTATION_PLAN.md
├── README.md
├── requirements.txt
└── main.py
```

这是目标结构，不要求在项目开始阶段一次性建立全部文件。

---

# 12. 项目阶段

```text
Phase 0
项目基线与环境检查

Phase 1
数据清洗 + SQLite + SQL

Phase 2
KPI + 多维经营分析

Phase 3
销售 / 需求预测

Phase 4
库存异常预警

Phase 5
Power BI

Phase 6
测试 + 文档 + 重构

Phase 7
最终 GitHub 整理
```

---

# 13. 测试策略

项目核心函数必须具有基础单元测试。

重点覆盖：

```text
数据去重
缺失值处理
分类字段标准化
Revenue 计算
MoM Growth
Inventory Turnover
MAE
RMSE
Inventory Risk Classification
```

最终要求：

```bash
pytest
```

能够正常运行。

---

# 14. Codex 使用规范

Codex 的角色：

- 阅读代码
- 分析现有结构
- 编写代码
- 重构代码
- 编写测试
- 运行测试
- 检查错误
- 更新文档

Codex 不应该：

- 一次性重写整个项目
- 编造业务数据结果
- 编造模型指标
- 假装 synthetic data 是真实企业数据
- 未运行代码就声称结果正确
- 未检查现有结构就删除原项目重要内容

---

# 15. Git 提交策略

每一个阶段至少一个主要 commit。

示例：

```text
feat: build cleaned data pipeline and SQLite analytics layer

feat: add business KPI and multidimensional analytics

feat: add demand forecasting and model evaluation

feat: add inventory risk alert system

feat: prepare Power BI analytics dataset

test: add automated validation tests

docs: finalize project documentation
```

---

# 16. 项目验收标准

项目最终完成时，应满足：

## 数据层

- 原始数据与处理数据分离
- 数据清洗过程可重复运行
- SQLite 可以重新生成
- 关键字段具有合理校验

## SQL

- 至少覆盖销售、库存、产品、区域和供应商分析
- 查询可以正常运行
- 输出结果与 Python 指标基本一致

## Python

- 模块职责清晰
- 不将所有逻辑继续堆积在一个 analysis.py
- 主要功能可以通过统一入口执行

## Machine Learning

- 有 baseline
- 有至少两个模型
- 使用时间顺序划分
- 使用 MAE 和 RMSE
- 不存在明显数据泄漏
- 报告基于实际运行结果

## Inventory Alert

- 状态规则明确
- 风险结果可解释
- 输出结构适合 Power BI 使用

## Power BI

- 有 Power BI-ready 数据集
- 有 KPI / DAX 说明
- 有 Dashboard 页面规划

## Testing

- 核心函数有测试
- pytest 可以正常执行

## Documentation

至少存在：

```text
README.md
PROJECT_INTRODUCTION.md
PROJECT_MASTER_PLAN.md
PHASED_IMPLEMENTATION_PLAN.md
DATA_QUALITY_REPORT.md
MODEL_EVALUATION.md
BUSINESS_INSIGHTS.md
POWER_BI_GUIDE.md
```

---

# 17. 数据与项目边界声明

本项目：

- 使用公开项目作为学习基础
- 使用 synthetic data
- 不包含华立集团真实经营数据
- 不声称项目数据来源于真实企业内部系统
- 不将模型结果描述为生产环境效果
- 主要用于展示企业数据分析与 AI 场景验证流程

---

# 18. 最终目标

项目完成后，应能够通过一个清晰的 GitHub Repository 展示以下能力：

```text
SQL
+
Python
+
Pandas
+
Data Cleaning
+
Business KPI
+
Data Visualization
+
Machine Learning
+
MAE / RMSE
+
Inventory Risk
+
Power BI
+
Testing
+
Git / GitHub
```

最终形成一个既能运行、又能解释、还具有完整业务流程的小型企业经营数据智能分析项目。
