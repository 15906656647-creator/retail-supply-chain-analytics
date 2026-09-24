# Business Insights — Phase 2

## 1. Executive Summary

**Fact:** Synthetic revenue was 336,627,819.99 across 149,949 generated single-item orders and 705,399 units. The weekly record stockout rate was 1.77%.
**Interpretation:** These figures describe a synthetic demonstration dataset, not actual company performance.

## 2. Analysis Scope

Cumulative KPIs include sales dated 2025-01-06 through 2026-01-04. Inventory covers 52 weeks starting 2025-01-06. Complete calendar months: 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12. Partial months: 2025-01, 2026-01. A synthetic order contains one product row, so AOV is a single-item proxy.

## 3. Sales Performance

**Fact:** Synthetic AOV proxy was 2,244.95; synthetic average selling price was 477.22. Among complete months, 2025-10 had the highest synthetic revenue (31,696,260.43) and 2025-11 the lowest (24,720,918.60).
**Fact:** The strongest revenue MoM increase was 2025-10 (27.94%); the weakest was 2025-11 (-22.01%). Both compare complete months.

## 4. Inventory Performance

**Fact:** Lost sales units were 4,238, with estimated catalog-price value 2,123,037.85. Spoilage units were 46,813, with estimated cost 6,199,271.58. Approximate inventory turnover was 14.33.
**Interpretation:** The turnover ratio is an analytical proxy based on weekly closing stock and synthetic unit costs; it is not an audited financial ratio.

## 5. Product and Category Insights

**Fact:** Toilet Paper (6 pack) led product synthetic revenue (45,750,683.88); Energy Drink Can led units (37,513). Biscuits Family Pack had the highest weekly record stockout rate (3.85%); Energy Drink Can had the most lost sales units (413).
**Fact:** Household Essentials led category revenue with 40.46% of synthetic revenue and 21.22% of units.

## 6. Regional and Store Insights

**Fact:** East led regions with synthetic revenue 90,696,196.69 and 26.94% share. East Flagship 9 led stores with 41,303,881.90. Latest East inventory held 15,479 units valued at 4,202,298.39.

## 7. Supplier View

**Fact:** Products linked to Packaged Supplier 1 had the highest supplier-associated weekly record stockout rate (3.38%). Its product count was 3, static reliability score 0.85, and static average lead time 10 days.
**Interpretation:** This is an association in synthetic data. No purchase transaction history supports a claim about delivery performance or causation.

## 8. Data and Metric Limitations

- Transactions, prices and discounts are synthetic; revenue is not actual company revenue.
- Each synthetic order is a single-item row; AOV is not a customer basket measure.
- Partial calendar months (2025-01, 2026-01) are excluded from formal MoM.
- Inventory accounting semantics for opening stock and receipts remain unresolved.
- Supplier reliability and lead time are static synthetic attributes.
- Stockout and fill rate use weekly record flags, not orders; turnover is approximate.

## 9. Implications for Phase 3

The reconciled historical sales quantities by order date, inventory week, store and product provide a consistent input base for later forecasting work. No forecasting model is trained in Phase 2.
