# Phase 0 Baseline and Implementation Plan

本文件记录 2026-09-24 对原始公开项目的检查结果，并仅规划下一阶段的数据层工作。仓库数据是 synthetic data，不代表任何企业的真实经营数据。以下将**已有实现**与上一级目录中的项目规划分开描述。

## 1. Current Repository Overview

实际 Git 仓库是 `retail-supply-chain-analytics/`，而不是其上一级工作目录。规划文档位于仓库外的上一级目录：`项目介绍.md`、`项目总纲.md`、`项目分阶段操作流程.md`；仓库内没有相应英文文件名的副本。

```text
库存智能分析系统/
├── 项目介绍.md                         # 项目定位与目标；仓库外
├── 项目总纲.md                         # 目标架构、数据模型、KPI；仓库外
├── 项目分阶段操作流程.md               # Phase 0–7 计划；仓库外
└── retail-supply-chain-analytics/      # 实际 Git 仓库
    ├── analysis.py                     # 当前唯一 Python 运行入口
    ├── README.md                       # 原项目说明、运行命令、既有结论
    ├── SUPPLY_CHAIN_RECOMMENDATIONS.md  # 原项目的供应链建议
    ├── IMPLEMENTATION_PLAN.md          # 本基线及后续规划
    ├── retail-supply-chain-dashboard.pbix # 已有 Power BI 二进制报表
    ├── data/
    │   ├── inventory_ledger.csv        # 原始周度库存台账
    │   ├── inventory_ledger_clean.csv  # analysis.py 的清洗输出
    │   ├── stores.csv                  # 门店维表
    │   ├── products.csv                # 产品维表与目录价格
    │   ├── suppliers.csv               # 供应商维表
    │   ├── powerbi_dataset.csv         # 关联后的周度宽表输出
    │   └── summary_metrics.csv         # 单项汇总指标输出
    ├── sql/
    │   └── schema_and_queries.sql      # 四张表的 DDL 和十项查询
    ├── powerbi/
    │   └── POWER_BI_GUIDE.md           # 导入、DAX 与三页看板指南
    └── images/                          # analysis.py 生成的六张 PNG
        ├── stockout_rate_by_category.png
        ├── stockout_rate_by_region.png
        ├── inventory_turnover_by_category.png
        ├── supplier_lead_time_vs_stockouts.png
        ├── demand_forecast_vs_actual.png
        └── spoilage_cost_by_category.png
```

`analysis.py` 在模块顶层直接执行读取、清洗、关联、计算、绘图与导出，没有独立 CLI、统一配置或测试入口。其相对路径假定当前工作目录为仓库根目录。原项目没有 SQLite 数据库文件、销售订单表、`src/`、`tests/` 或依赖管理文件。

## 2. Current Data Model

以下类型是用当前 Python/pandas 读取 CSV 时推断的类型；CSV 本身不声明类型。全部日期位于 2025-01-06 至 2025-12-29 的 52 个周起始日，日期解析检查没有发现无效值。`store_id`、`product_id`、`supplier_id` 分别与对应维表关联；原始和清洗台账的候选行键为 `(store_id, product_id, week_start)`。清洗台账与三个维表的关联键没有未匹配值，台账中的 `supplier_id` 与产品目录一致。类别也与产品目录一致，但原始台账须先去空格并统一大小写。

| 文件 | 行 × 列 | 全部字段与类型 | 候选键、角色及质量结果 |
|---|---:|---|---|
| `inventory_ledger.csv` | 17,417 × 14 | 文本：`store_id`, `product_id`, `category`, `week_start`, `supplier_id`；整数：`opening_stock`, `spoilage_units`, `units_sold`, `closing_stock`, `stockout_flag`, `lost_sales_units`, `reorder_point`, `safety_stock`；浮点：`units_received` | 周度事实表；`week_start` 为日期，三个 ID 为外键候选。整行重复 257 条，恰对应复合键重复；`units_received` 缺失 519 个；`category` 有 15 种原始写法，规范化后为 5 类。 |
| `inventory_ledger_clean.csv` | 17,160 × 14 | 与原始台账相同 | 由原脚本去重、规范类别、以 0 填补 `units_received` 后导出。复合键唯一；无缺失、无整行重复。 |
| `stores.csv` | 16 × 4 | 文本：`store_id`, `store_name`, `region`, `store_type` | `store_id` 唯一；4 个区域、3 种门店类型；无缺失或重复。 |
| `products.csv` | 30 × 6 | 文本：`product_id`, `product_name`, `category`, `supplier_id`；浮点：`unit_cost`, `unit_price` | `product_id` 唯一，`supplier_id` 为外键候选；5 个品类；无缺失或重复；所有目录价格均不低于成本。 |
| `suppliers.csv` | 10 × 5 | 文本：`supplier_id`, `supplier_name`, `category`；整数：`avg_lead_time_days`；浮点：`reliability_score` | `supplier_id` 唯一；无缺失或重复；`avg_lead_time_days` 是时长而非日期。 |
| `powerbi_dataset.csv` | 17,160 × 26 | 文本：`store_id`, `store_name`, `region`, `store_type`, `product_id`, `product_name`, `category`, `week_start`, `supplier_id`；整数：`opening_stock`, `spoilage_units`, `units_sold`, `closing_stock`, `stockout_flag`, `lost_sales_units`, `reorder_point`, `safety_stock`, `avg_lead_time_days`；浮点：`units_received`, `lost_sales_value`, `reliability_score`, `unit_cost`, `unit_price`, `inventory_value`, `cogs`, `spoilage_cost` | 清洗台账关联维表后的派生宽表；候选行键同台账。无缺失或重复；`week_start` 为日期，价格、损失、库存价值及 COGS 为数值。它不是新增的独立销售事实表。 |
| `summary_metrics.csv` | 11 × 2 | 文本：`Unnamed: 0`, `0`（混合数值与文字使值列按文本读取） | 指标名列唯一，无缺失或重复。由 `pd.Series.to_csv()` 导致表头缺乏业务含义；不是交易或事实表。 |

数值基础检查未发现库存数量、损耗数量、销量、价格或成本为负；`stockout_flag` 仅为 0/1，供应商提前期为 6–21 天，可靠性分数为 0.83–0.97。仅凭 synthetic data 无法给所有极值设可靠的业务异常阈值。已发现的明确异常是：清洗台账中 4,904 行若按 `opening_stock + units_received - spoilage_units - units_sold = closing_stock` 核算则不平衡；这些行恰好是全部非零收货行，且差额等于 `units_received`。反而所有 17,160 行满足**不计收货**的等式。另有 9 行 `closing_stock = 0` 但 `stockout_flag = 0`。不能在未确认生成规则和字段口径前直接改写原始值。

现有数据对拟议指标的支持程度：

| 指标或分析 | 当前可支持程度与缺口 |
|---|---|
| Revenue | 可用 `units_sold × products.unit_price` 估算目录价销售额；没有实际成交价、折扣、退款或销售流水，不能称为实际 Revenue。 |
| Orders | 不可计算；缺少 `order_id` 和订单明细。AOV 同样不可计算。 |
| Units Sold | 可汇总周度台账的 `units_sold`；它不是逐笔交易数据。 |
| Inventory Level | 可用每个门店与商品的最新 `closing_stock` 表示周末库存快照；库存平衡口径须核实。 |
| Inventory Turnover | 已可按 `units_sold × unit_cost / 平均(closing_stock × unit_cost)` 做近似年度周转；不是经审计的财务 COGS/平均存货口径。 |
| Stockout Rate | 可按 `stockout_flag` 的周度记录比例计算；零库存与标记的 9 行差异需核实。 |
| Supplier Analysis | 可按 `supplier_id` 关联静态提前期和可靠性分数、缺货率；缺少逐次采购、承诺及实际到货记录，不能验证真实交付绩效。 |
| Sales Forecasting | 可对周度 `units_sold` 做示例预测；缺订单级销售、促销和价格历史，缺货时销量还可能低估需求。 |

## 3. Existing Features

**Python：** `analysis.py` 读取原始台账及三张维表，删除整行重复、规范台账品类、将缺失收货量填 0，再计算 fill/stockout rate、估算 lost sales value、库存周转和库存天数、品类/区域/门店类型缺货率、供应商相关性以及品类损耗成本。运行时打印结果，覆盖三个现有输出 CSV 和六张 PNG。`summary_metrics.csv` 包含 11 项汇总指标。

**SQL：** `sql/schema_and_queries.sql` 定义 `stores`、`products`、`suppliers`、`inventory_ledger` 四张表，并写有十项查询：总体缺货与 fill rate、品类及区域缺货、损失销售额前十商品、供应商评分表、低于安全库存的周记录、损耗、月度缺货趋势、门店类型表现、低于补货点的商品。仓库未提供建库脚本或已建数据库；SQL 中没有订单/销售额分析。脚本中的 SQLite `strftime` 也意味着“跨数据库直接通用”的说法需要验证。

**Power BI：** `data/powerbi_dataset.csv` 是现成的周度平面数据集；指南给出了导入字段类型、DAX 指标、Executive Overview、Supplier Scorecard、Inventory Health 三页布局和可选星型模型关系。仓库还实际跟踪 `retail-supply-chain-dashboard.pbix`，内部报表定义包含这三页；本阶段没有在 Power BI Desktop 中打开或验证模型刷新。README 和指南中“没有 `.pbix`”的说明与仓库现状不一致。

**Forecasting：** 已有按全年总销量选一个商品、使用前四周移动平均预测下一周销量的演示；`shift(1)` 避免了单次预测直接读取目标周，但选品使用了全期数据。脚本计算并打印 MAPE（临时运行得到 7.2%），生成实际值对比图；没有预测结果 CSV、时间切分、naive/线性回归/随机森林比较或 MAE/RMSE。

**Inventory Analytics：** 已有缺货、低于安全库存的 SQL 查询、周转、损耗、供应商静态属性关联和建议文档；尚无结合预测需求的 `NORMAL`/`LOW_STOCK`/`STOCKOUT_RISK`/`OVERSTOCK` 分类及风险原因输出。

**Testing/Dependencies：** 没有测试文件、`requirements.txt`、`pyproject.toml`、`Pipfile` 或环境配置。脚本实际只导入 pandas、NumPy、Matplotlib；scikit-learn 与 pytest 是目标项目后续阶段所需，不是原脚本依赖。

## 4. Gap Analysis

上一级 `项目总纲.md` 与 `项目分阶段操作流程.md` 描述的是**最终目标**，不能当作现有功能。当前只有原项目的周度库存分析流程。目标中的原始/处理数据分层、可重建 SQLite、销售订单事实表、经营 SQL、正式 KPI 和多维经营宽表都尚未实现。销售相关 Revenue、Orders、AOV、月环比指标缺少交易基础，其中 Orders 无法从库存台账推导。

后续阶段目标还包括时间顺序训练/测试、naive/Linear Regression/Random Forest 对比、MAE/RMSE、预测结果表、库存风险状态和解释、五页经营 Power BI 看板、自动化入口、pytest 与业务报告。现有单品移动平均图、三页原供应链报表及静态建议文档不能替代这些交付物。Phase 0 不实现上述差距。

## 5. Technical Risks

- **库存口径冲突：** 所有非零 `units_received` 行在通常的库存收支等式下不平衡；Phase 1 必须查明该字段表示的时点或生成逻辑，再决定清洗与告警如何使用它。
- **经营指标来源不足：** 库存销量配目录价只能估算销售额，订单和实际成交信息完全缺失；静态 `reliability_score` 也不能充当逐笔准时交付事实。
- **清洗假设：** 将 519 个未知收货值直接填 0 是原脚本行为，可能把“未记录”误判为“未收货”；原始品类写法有 15 种。
- **预测解释：** 周度销量可能受缺货截断；演示在全期选取最高销量商品，不能作为无选择偏差的留出集评估或企业级预测效果。
- **脚本和输出：** 单文件顶层脚本依赖工作目录，运行会覆盖已跟踪的 CSV 和图表。`summary_metrics.csv` 的自动表头也不适合作稳定的数据接口。
- **SQL/Power BI 可复现性：** SQL 只有文本 DDL/查询；README 中 `SQL3` 示例及先导入后读建表脚本的顺序不是可直接依赖的完整建库流程。README/指南对 `.pbix` 是否存在的描述已经过时；尚未验证实际 Power BI 文件能否打开或刷新。
- **数据边界：** 全部数据为 synthetic，仅适合演示和方法验证，不能把相关性或 MAPE 解释为真实企业因果关系或生产环境表现。

## 6. Phase 1 Proposed Changes

Phase 1 只处理**数据结构、数据清洗、SQLite 和 SQL 分析**；开始前先固定原始数据的含义，特别是收货量与 `closing_stock` 的关系、`stockout_flag` 的定义以及销售数据缺口。

| 预计文件/目录 | 拟议作用 |
|---|---|
| `data/raw/`, `data/processed/`, `data/database/` | 分离只读原始输入、可重建清洗结果和 SQLite 产物；迁移时保留原 CSV，不直接覆盖。 |
| `src/data_cleaning.py` | 对缺失、重复、类型、日期和类别做可复现检查与清洗，记录异常及处理数量；不擅自修改尚未明确口径的库存数值。 |
| `src/database.py`、`sql/schema.sql` | 建立可重复生成的 SQLite 表、主外键及导入流程；先按已证实的数据建表。 |
| `sql/business_analysis.sql` | 增加可执行且可核对的数据层 SQL；涉及 Orders/Revenue 的查询须在明确销售事实表后实现，不用目录价估算冒充实际成交。 |
| `reports/DATA_QUALITY_REPORT.md` | 记录逐表质量、收货/库存平衡问题、处理规则与数据限制。 |
| `data/raw/sales.csv`（如 Phase 1 确认需要订单指标） | 只可作为明确标注、可重现生成规则的 synthetic 销售数据新增；不得与现有真实销售流水混淆。 |

保留 `analysis.py`、原项目 SQL、Power BI 文件、图表与建议文档作为可对照基线；若调整原脚本路径，只做兼容所需的最小改动。Phase 1 暂不建立正式 KPI 系统、预测模型、库存风险预警或新 Power BI 模型。

## 7. Recommended Target Structure

以下是**逐步创建的目标结构**，不是当前仓库结构，也不要求 Phase 0 一次建成。

```text
retail-supply-chain-analytics/
├── analysis.py                         # 保留原项目入口作为对照
├── data/
│   ├── raw/                            # Phase 1：原始 synthetic 输入
│   ├── processed/                      # Phase 1 起：清洗输出；后续加入 KPI/预测/预警
│   └── database/                       # Phase 1：可重建 SQLite 文件
├── src/
│   ├── data_cleaning.py                # Phase 1
│   ├── database.py                     # Phase 1
│   ├── kpi_analysis.py                 # Phase 2
│   ├── forecasting.py                  # Phase 3
│   └── inventory_alerts.py             # Phase 4
├── sql/
│   ├── schema_and_queries.sql          # 保留原项目文件
│   ├── schema.sql                      # Phase 1
│   └── business_analysis.sql           # Phase 1 起逐步扩充
├── reports/
│   ├── DATA_QUALITY_REPORT.md          # Phase 1
│   ├── BUSINESS_INSIGHTS.md            # 后续
│   └── MODEL_EVALUATION.md             # 后续
├── powerbi/                            # 保留原指南；后续更新
├── images/                             # 保留原图；后续增补
├── tests/                              # 后续阶段
├── requirements.txt                    # 后续阶段确认依赖后建立
└── main.py                             # 后续阶段统一入口
```

## 8. Phase 0 Verification Result

- **运行：** 在临时目录复制 `analysis.py` 与四个原始输入 CSV 后执行 `python analysis.py`，退出码 0；标准错误为空，没有观察到 warning 或 error。读取 `inventory_ledger.csv`、`stores.csv`、`products.csv`、`suppliers.csv`，产生 `inventory_ledger_clean.csv`、`summary_metrics.csv`、`powerbi_dataset.csv` 及六张图。未修改仓库中的 CSV。该次运行打印总体 fill rate 98.2%、stockout rate 1.8%，估算 lost sales value 2,123,038、spoilage cost 6,199,272；这些均是 synthetic data 计算结果。运行生成 Power BI 数据集；预测仅打印单品 MAPE 并绘图，没有预测结果文件或库存风险分类输出。
- **环境：** Python 3.11.4；pip 23.2.1。当前安装版本：pandas 2.3.3、NumPy 1.26.4、Matplotlib 3.11.2、scikit-learn 1.9.1、pytest 7.4.0。原脚本需要前三者；当前仓库无依赖管理文件，本阶段不创建。
- **Git：** 分支 `main`，检查前工作区 clean，跟踪 `origin/main`。`origin` 指向 `https://github.com/15906656647-creator/retail-supply-chain-analytics.git`；未配置 `upstream`。最近三次提交为 `810eeeb`、`7a8ca1d`、`0564eac`；未更改 Git 历史或推送。
- **阶段判断：** Phase 0 为 **PARTIAL**：原项目运行和数据基线验证通过，但原规划文档目前位于仓库外、`upstream` 缺失，Power BI 文件未在 Desktop 中验证。**Ready for Phase 1: YES**；无代码运行阻塞，Phase 1 应优先厘清库存收支口径、零库存标记差异与订单数据来源。Phase 0 不生成 synthetic data，不实现 Phase 1 功能。
