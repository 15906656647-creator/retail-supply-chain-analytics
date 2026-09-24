# 项目分阶段操作流程

## 1. 开发策略

本项目采用分阶段开发方式。

每个 Phase 只完成一个相对独立的目标，完成代码运行、测试和 Git 提交后，再进入下一阶段。

推荐 Git 工作流：

```text
main
│
├── phase-1-data-sql
├── phase-2-kpi-analysis
├── phase-3-forecasting
├── phase-4-inventory-alerts
├── phase-5-powerbi
└── phase-6-testing-docs
```

如果希望流程更简单，也可以一直在一个开发分支上操作，但每个 Phase 必须单独提交 commit。

---

# Phase 0：项目基线检查与环境准备

## 目标

确认原始项目可以运行，并建立后续二次开发基线。

## 操作步骤

### Step 1：检查 Git 状态

```bash
git status
git remote -v
git branch
```

确认：

- `origin` 指向自己的 Fork
- `upstream` 指向原项目
- 当前工作区没有异常修改

---

### Step 2：阅读原项目

重点阅读：

```text
README.md
analysis.py
sql/schema_and_queries.sql
powerbi/POWER_BI_GUIDE.md
SUPPLY_CHAIN_RECOMMENDATIONS.md
data/
```

---

### Step 3：安装基础依赖

建立虚拟环境：

```powershell
python -m venv .venv
```

PowerShell 激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装基础包：

```powershell
pip install pandas numpy matplotlib scikit-learn pytest
```

---

### Step 4：运行原始项目

```powershell
python analysis.py
```

确认原项目可以正常：

- 读取数据
- 清洗数据
- 计算 KPI
- 生成图表
- 输出 Power BI 数据集

---

### Step 5：建立基线提交

如果当前 Fork 与原项目完全一致，可保留当前状态。

建议建立开发分支：

```bash
git switch -c phase-1-data-sql
```

---

## Phase 0 验收标准

- 原项目成功运行
- 本地 Python 环境可用
- Git 远程仓库配置正确
- 已理解原项目目录结构
- 尚未进行大规模代码重写

---

# Phase 1：数据结构、SQLite、数据清洗与 SQL

## 目标

建立统一的数据层，为后续 KPI、机器学习和 Power BI 提供稳定输入。

---

## Step 1：检查现有数据结构

由 Codex 阅读：

```text
data/inventory_ledger.csv
data/stores.csv
data/products.csv
data/suppliers.csv
```

输出字段说明。

需要明确：

- 主键
- 外键
- 日期字段
- 数值字段
- 分类字段
- 缺失值
- 重复值

---

## Step 2：补充销售数据

如果原项目没有完整的销售订单表，则生成：

```text
data/raw/sales.csv
```

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

数据必须明确标记为 synthetic。

---

## Step 3：重构数据目录

目标结构：

```text
data/
├── raw/
├── processed/
└── database/
```

原则：

- raw 不直接修改
- processed 保存清洗结果
- database 保存 SQLite 文件

---

## Step 4：建立数据清洗模块

计划建立：

```text
src/data_cleaning.py
```

功能：

- remove_duplicates()
- handle_missing_values()
- normalize_categories()
- normalize_dates()
- validate_numeric_columns()
- check_outliers()
- merge_business_tables()

输出：

```text
data/processed/clean_business_data.csv
```

---

## Step 5：建立 SQLite 数据库

建立：

```text
src/database.py
```

数据库：

```text
data/database/business_analytics.db
```

核心表：

```text
stores
products
suppliers
sales
inventory
```

---

## Step 6：编写 SQL

建立：

```text
sql/business_analysis.sql
```

至少包含：

1. 月销售额
2. 月订单量
3. 月销量
4. 产品销售排名
5. 品类销售排名
6. 区域销售排名
7. 库存水平
8. 库存周转
9. 缺货率
10. 月环比增长率
11. 供应商表现
12. 高风险库存商品

---

## Step 7：生成数据质量报告

输出：

```text
reports/DATA_QUALITY_REPORT.md
```

包括：

- 原始记录数量
- 清洗后记录数量
- 缺失值处理
- 重复值处理
- 字段标准化
- 异常值检查
- 数据限制

---

## Phase 1 测试

至少验证：

```bash
python -m src.database
python -m src.data_cleaning
```

并执行 SQL 检查。

---

## Phase 1 Git

```bash
git status
git add .
git commit -m "feat: build cleaned data pipeline and SQLite analytics layer"
git push -u origin phase-1-data-sql
```

---

# Phase 2：经营 KPI 与多维分析

## 目标

建立完整的经营指标体系。

---

## Step 1：建立 KPI 模块

建立：

```text
src/kpi_analysis.py
```

核心指标：

```text
Revenue
Orders
Units Sold
Average Order Value
MoM Growth
Inventory Turnover
Stockout Rate
Fill Rate
Supplier Reliability
```

---

## Step 2：建立分析维度

至少支持：

```text
time
product
category
store
region
supplier
```

---

## Step 3：生成经营分析结果

输出：

```text
data/processed/monthly_kpi.csv
data/processed/product_kpi.csv
data/processed/region_kpi.csv
data/processed/supplier_kpi.csv
```

---

## Step 4：生成基础图表

输出到：

```text
images/
```

例如：

- monthly_revenue_trend.png
- product_sales_ranking.png
- regional_sales.png
- inventory_turnover.png
- stockout_rate.png

---

## Step 5：生成商业分析初稿

输出：

```text
reports/BUSINESS_INSIGHTS.md
```

要求：

- 所有数字来自程序计算
- 明确分析时间范围
- 区分事实和解释
- 不编造企业背景

---

## Phase 2 Git

```bash
git add .
git commit -m "feat: add business KPI and multidimensional analytics"
git push
```

---

# Phase 3：销售 / 需求预测模型

## 目标

验证销售预测 AI 场景是否可行。

---

## Step 1：建立预测数据集

根据：

```text
date
product_id
store_id
quantity
revenue
```

建立时间序列数据。

---

## Step 2：构造特征

至少包含：

```text
lag_1
lag_7
rolling_mean_7
rolling_mean_30
month
week_of_year
```

注意：

滚动特征必须避免未来数据泄漏。

---

## Step 3：时间顺序划分数据

禁止：

```python
train_test_split(..., shuffle=True)
```

建议：

```text
前 80% 时间 → training set
后 20% 时间 → test set
```

---

## Step 4：建立基线

Naive Baseline 示例：

```text
Tomorrow Demand = Previous Period Demand
```

必须先计算基线结果。

---

## Step 5：训练模型

至少：

```text
LinearRegression
RandomForestRegressor
```

---

## Step 6：模型评价

使用：

```text
MAE
RMSE
```

输出类似：

| Model | MAE | RMSE |
|---|---:|---:|
| Naive | ... | ... |
| Linear Regression | ... | ... |
| Random Forest | ... | ... |

---

## Step 7：输出模型结果

建立：

```text
src/forecasting.py
reports/MODEL_EVALUATION.md
data/processed/forecast_results.csv
```

报告包括：

- 数据划分
- 特征
- 模型
- MAE
- RMSE
- 基线比较
- 模型限制
- 是否适合进一步用于库存预警

---

## Phase 3 Git

```bash
git add .
git commit -m "feat: add demand forecasting and model evaluation"
git push
```

---

# Phase 4：库存异常与缺货风险预警

## 目标

将预测结果转化为可解释的业务预警。

---

## Step 1：设计安全库存规则

考虑：

```text
forecast_demand
current_stock
average_demand
supplier_lead_time
safety_stock
```

---

## Step 2：定义库存状态

建议：

```text
NORMAL
LOW_STOCK
STOCKOUT_RISK
OVERSTOCK
```

每一个状态必须有明确规则。

---

## Step 3：建立预警模块

```text
src/inventory_alerts.py
```

输出：

```text
data/processed/inventory_alerts.csv
```

建议字段：

```text
product_id
store_id
current_stock
forecast_demand
safety_stock
risk_status
risk_reason
```

---

## Step 4：检查预警合理性

检查：

- 是否存在全部商品都被标记成同一种状态
- 阈值是否过于极端
- forecast 是否正确关联商品
- 库存量是否存在负值
- 输出原因是否可解释

---

## Phase 4 Git

```bash
git add .
git commit -m "feat: add inventory risk alert system"
git push
```

---

# Phase 5：Power BI 数据层与 Dashboard

## 目标

把 Python / SQL 分析结果转换成 Power BI 可用的数据模型。

---

## Step 1：建立 Power BI 数据集

输出：

```text
data/processed/powerbi_business_dataset.csv
```

---

## Step 2：设计 Dashboard

推荐页面：

### Page 1 — Executive Overview

- Revenue
- Orders
- Units Sold
- MoM Growth
- Stockout Rate

### Page 2 — Sales Performance

- Revenue Trend
- Product Ranking
- Category Ranking
- Region Comparison

### Page 3 — Inventory Health

- Inventory Level
- Inventory Turnover
- Stockout Rate
- Risk Status

### Page 4 — Supplier Performance

- Lead Time
- Reliability
- Fill Rate
- Supplier Ranking

### Page 5 — Forecast & Alerts

- Actual vs Forecast
- Forecast Error
- Stockout Risk
- Low Stock Items

---

## Step 3：建立 Power BI 文档

更新：

```text
powerbi/POWER_BI_GUIDE.md
```

包括：

- 数据导入
- 数据类型
- Relationships
- DAX Measures
- Dashboard Layout
- Filter / Slicer
- 页面说明

---

## Phase 5 Git

```bash
git add .
git commit -m "feat: prepare Power BI analytics dataset and dashboard guide"
git push
```

---

# Phase 6：测试、重构与项目文档

## 目标

使项目从“能运行”提升到“结构清楚、结果可验证”。

---

## Step 1：建立测试目录

```text
tests/
```

测试：

```text
test_data_cleaning.py
test_kpi_analysis.py
test_forecasting.py
test_inventory_alerts.py
```

---

## Step 2：重点测试

例如：

- duplicate removal
- missing value handling
- revenue calculation
- MoM calculation
- inventory turnover
- MAE / RMSE calculation
- risk status classification

---

## Step 3：建立 requirements

```text
requirements.txt
```

---

## Step 4：整理主 README

最终 README 至少包含：

1. Business Problem
2. Original Project
3. Dataset
4. Architecture
5. Data Cleaning
6. SQLite / SQL Analysis
7. KPI System
8. Forecasting
9. Model Evaluation
10. Inventory Alerts
11. Power BI
12. Project Structure
13. How to Run
14. Results
15. Limitations
16. Data Disclaimer

---

## Step 5：运行最终测试

```bash
pytest
```

运行完整项目：

```bash
python main.py
```

如果没有 `main.py`，则在最后阶段创建统一入口。

---

## Phase 6 Git

```bash
git add .
git commit -m "test: add validation tests and finalize project documentation"
git push
```

---

# Phase 7：最终项目整理

## 目标

形成可展示的 GitHub 项目。

---

## 最终检查

### Git

```bash
git status
git log --oneline
```

### Python

```bash
pytest
python main.py
```

### 数据

确认：

- 原始数据存在
- 清洗数据存在
- 数据库存在或可生成
- Power BI 数据存在
- forecast 数据存在
- inventory alerts 存在

### 文档

确认：

```text
README.md
PROJECT_INTRODUCTION.md
PROJECT_MASTER_PLAN.md
PHASED_IMPLEMENTATION_PLAN.md
reports/DATA_QUALITY_REPORT.md
reports/MODEL_EVALUATION.md
reports/BUSINESS_INSIGHTS.md
powerbi/POWER_BI_GUIDE.md
```

---

# 推荐的 Codex 使用规则

每个阶段开始时，先向 Codex 提出：

```text
请先阅读当前 repository 以及与本阶段有关的文件。

不要立即修改代码。

先说明：
1. 当前已有功能
2. 当前数据结构
3. 本阶段需要修改哪些文件
4. 是否存在数据或设计风险
5. 你的实施步骤

确认分析完成后，再执行当前 Phase。

不要提前实现后续 Phase。
```

每个阶段完成后要求 Codex：

```text
请运行本阶段相关代码和测试。

然后总结：
1. 修改了哪些文件
2. 新增了哪些文件
3. 实现了哪些功能
4. 测试是否通过
5. 当前输出文件在哪里
6. 还存在什么限制

不要继续下一阶段。
```

这样可以避免 Codex 一次性重写整个项目，并使每一次 Git commit 都具有清晰含义。
