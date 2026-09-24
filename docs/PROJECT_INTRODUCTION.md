# 企业经营数据智能分析与 AI 应用场景评估项目

## 1. 项目名称

**中文名称：** 企业经营数据智能分析与 AI 应用场景评估项目  
**英文名称：** Enterprise Sales & Inventory Intelligence System

本项目基于一个公开的零售库存与供应链分析 GitHub 项目进行二次开发，在保留原项目 SQL、Python、Pandas、Power BI 和库存分析基础能力的前提下，进一步扩展为一个更完整的企业经营数据分析与 AI 场景验证项目。

---

## 2. 原始 GitHub 项目

原始项目名称：

**Retail Inventory & Supply Chain Analytics (SQL + Python + Power BI)**

原始项目地址：

https://github.com/DataWithSoumya/retail-supply-chain-analytics

原始项目作者：

**DataWithSoumya**

原始项目主要围绕零售企业库存与供应链分析展开，包含：

- Python / Pandas 数据清洗与指标计算
- SQL 表结构与业务查询
- 库存缺货分析
- 库存周转分析
- 供应商表现分析
- 损耗 / spoilage 分析
- 简单的需求预测
- Power BI 数据集与看板搭建指南

原始项目使用的是 **synthetic data（合成数据）**，用于作品集和演示，不代表任何真实企业经营数据。

---

## 3. 本项目的二次开发目标

本项目不直接照搬原项目，而是在原项目基础上重新组织数据流程、业务指标体系和 AI 验证模块，使其形成一套更接近企业信息化部门实际工作流程的小型完整项目。

目标流程如下：

```text
原始经营数据
    ↓
数据质量检查
    ↓
Python / Pandas 数据清洗
    ↓
SQLite 数据库
    ↓
SQL 经营分析
    ↓
经营宽表与 KPI 指标体系
    ↓
多维经营分析
    ↓
销售 / 需求预测模型
    ↓
MAE / RMSE 模型评估
    ↓
库存异常与缺货风险预警
    ↓
Power BI 数据集
    ↓
经营分析报告与模型评估报告
```

---

## 4. 与实习任务的对应关系

本项目重点覆盖以下企业经营数据分析任务：

### 4.1 经营数据提取

通过 SQLite 和 SQL 对销售、产品、门店、供应商、库存等业务数据进行组织，并编写经营分析查询。

计划覆盖：

- 销售额
- 订单量
- 产品销量
- 区域销售
- 库存水平
- 库存周转
- 缺货情况
- 供应商表现
- 月度变化趋势

---

### 4.2 数据清洗与标准化

使用 Python 和 Pandas 完成：

- 缺失值检查与处理
- 重复记录识别和删除
- 日期格式标准化
- 分类字段标准化
- 数值字段类型校验
- 异常值检查
- 多表关联
- 数据质量报告输出

---

### 4.3 多维经营分析

从以下维度分析经营数据：

- 时间
- 产品
- 品类
- 门店
- 区域
- 供应商

主要 KPI 包括：

- Revenue
- Orders
- Units Sold
- Average Order Value
- Month-over-Month Growth
- Inventory Turnover
- Stockout Rate
- Fill Rate
- Supplier Reliability

---

### 4.4 Power BI 可视化

生成适合直接导入 Power BI 的经营宽表。

计划制作以下页面：

1. Executive Overview
2. Sales Performance
3. Inventory Health
4. Supplier Performance
5. Forecast & Inventory Alerts

看板重点展示：

- 销售额
- 订单量
- 销量
- 环比变化
- 产品排名
- 区域表现
- 库存水平
- 缺货率
- 库存周转
- 库存风险状态

---

### 4.5 AI 应用场景验证

本项目的 AI 部分主要用于验证两个业务场景：

#### 场景 A：销售 / 需求预测

基于历史销售数据构造时间序列特征，例如：

- lag_1
- lag_7
- rolling_mean_7
- rolling_mean_30
- month
- week_of_year

至少比较以下方法：

- Naive Baseline
- Linear Regression
- Random Forest Regressor

评价指标：

- MAE
- RMSE

---

#### 场景 B：库存异常与缺货风险预警

结合：

- 预测需求
- 当前库存
- 安全库存
- 历史销售水平

对商品库存状态进行分类，例如：

- NORMAL
- LOW_STOCK
- STOCKOUT_RISK
- OVERSTOCK

---

## 5. 技术栈

| 模块 | 技术 |
|---|---|
| 数据处理 | Python |
| 数据分析 | Pandas / NumPy |
| 数据库 | SQLite |
| SQL 分析 | SQL |
| 机器学习 | scikit-learn |
| 可视化 | Matplotlib |
| 商业智能 | Power BI |
| 测试 | pytest |
| 版本控制 | Git / GitHub |
| AI 编程辅助 | Codex |

---

## 6. 数据说明

原始 GitHub 项目使用模拟生成的零售与库存数据。

本项目后续如需要补充销售订单、采购记录或预测训练数据，同样采用 **synthetic data**。

所有模拟数据必须满足以下原则：

1. 明确标注为 synthetic data。
2. 不冒充华立集团或任何真实公司的内部经营数据。
3. 不包含真实客户、供应商、员工或商业敏感信息。
4. 仅用于学习、项目开发和作品集展示。

---

## 7. 项目预期成果

项目最终计划形成以下成果：

### 数据成果

- 清洗后的经营数据
- SQLite 数据库
- 经营分析宽表
- Power BI 数据集
- 库存预警结果

### 代码成果

- 数据清洗模块
- 数据库构建模块
- KPI 分析模块
- 销售预测模块
- 库存预警模块
- 自动化数据处理入口
- pytest 测试

### 文档成果

- 项目介绍
- 项目实施总纲
- 分阶段实施计划
- 数据质量报告
- 模型评估报告
- 商业分析报告
- Power BI 搭建指南
- README

---

## 8. 项目开发原则

### 原则 1：先理解，后修改

Codex 在每个开发阶段开始前，应先阅读现有代码、数据和文档，再提出修改方案。

### 原则 2：分阶段开发

项目不一次性重写，而是按照 Phase 分阶段完成。

每个阶段均应遵循：

```text
阅读现有项目
→ 制定当前阶段计划
→ 修改代码
→ 本地运行
→ 检查输出
→ 运行测试
→ git status
→ git commit
→ git push
```

### 原则 3：结果必须来自代码计算

报告中的数值、KPI、模型指标和商业结论应来自实际运行结果，禁止手工编造。

### 原则 4：保留可解释性

机器学习部分重点体现：

- 为什么使用该模型
- 输入特征是什么
- 如何划分训练集与测试集
- MAE / RMSE 的结果
- 模型与基线相比是否改善

而不是单纯追求复杂模型。

---

## 9. 最终项目定位

本项目定位为一个：

> **小型、完整、可运行、可解释的企业经营数据分析与 AI 场景验证项目。**

重点不是构建复杂的生产级系统，而是展示从业务问题到数据处理、SQL 分析、KPI 构建、可视化、预测建模、库存预警和报告输出的完整工作流程。
