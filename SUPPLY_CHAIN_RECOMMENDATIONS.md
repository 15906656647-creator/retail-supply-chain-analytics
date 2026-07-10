# Supply Chain Recommendations

Actionable moves derived from the stockout, supplier, spoilage, and
forecasting analysis in `analysis.py`.

## 1. Fix the Real Driver: Supplier Reliability, Not Lead Time

The data shows something worth double-checking your assumptions on: stockout
rate correlates **negatively** with supplier lead time (-0.45) — slower
suppliers aren't causing more stockouts. That's because reorder points are
already sized up for longer lead times, and it's working. The stronger,
more useful signal is **reliability** (-0.44 correlation, in the expected
direction): suppliers with lower on-time delivery rates (e.g. `SUP003` at
85%, `SUP005`/`SUP006` at 83%) drive more stockouts regardless of how fast
they normally are.

**Recommendation:** Don't renegotiate for faster lead times — renegotiate
(or diversify away from) suppliers with the lowest reliability scores.
A dependable 21-day supplier is safer than an unreliable 6-day one once
reorder points account for the lead time.

## 2. Category-Specific Stockout Fixes

- **Packaged Foods** has the highest stockout rate (2.2%) despite not being
  perishable — this looks like a reorder-point sizing issue, not a supply
  constraint. Recommend reviewing reorder points for this category first.
- **Personal Care** has the lowest stockout rate (1.3%) — current policy is
  working well here; use it as the internal benchmark for other categories.

## 3. Spoilage Is Concentrated and Fixable

Perishables account for the large majority of total spoilage cost — by far
the highest of any category. Since spoilage here comes from unsold stock
sitting too long (aging inventory), the fix is tighter ordering, not more
safety stock:

**Recommendation:** For Perishables specifically, shrink the safety-stock
buffer and order more frequently in smaller batches, even if it slightly
raises stockout risk — the spoilage cost is the bigger loss to eliminate for
short-shelf-life goods.

## 4. West Region Needs a Closer Look

West has the joint-highest stockout rate by region. Cross-reference which
suppliers serve West-region stores specifically — if it's dominated by one
or two lower-reliability suppliers, this may be a sourcing/regional
allocation issue rather than a store-operations issue.

## 5. Demand Forecasting Is a Cheap Win

A simple 4-week moving average forecast on the highest-volume product hit a
~7% MAPE (mean absolute percentage error) — quite accurate for something
this simple. This suggests a lightweight, low-maintenance forecasting layer
(no need for a complex ML model) could meaningfully improve reorder timing
across the catalog, especially ahead of the festive-season demand spike.

## Possible Next Steps

- Build a simple safety-stock optimization: safety stock ∝ supplier
  reliability, not a flat percentage of demand as currently modeled
- Extend the moving-average forecast to every SKU and feed it directly into
  the reorder-point calculation instead of a static formula
- Add supplier cost data to weigh "switch suppliers" recommendations against
  the cost of doing so, not just service level
- A/B test smaller, more frequent Perishables orders on a subset of stores
  before rolling out chain-wide

---
*Note: Dataset is synthetically generated for portfolio/demonstration purposes and does not represent a real business.*
