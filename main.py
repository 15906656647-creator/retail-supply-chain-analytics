"""Run the validated Phase 1–5 analytical pipeline in dependency order."""

from src import (
    data_cleaning,
    synthetic_sales,
    database,
    kpi_analysis,
    forecasting,
    inventory_alerts,
    powerbi_dataset,
)


STAGES = (
    ("Phase 1", "Data Cleaning", data_cleaning),
    ("Phase 1", "Synthetic Sales", synthetic_sales),
    ("Phase 1", "Database", database),
    ("Phase 2", "KPI Analysis", kpi_analysis),
    ("Phase 3", "Forecasting", forecasting),
    ("Phase 4", "Inventory Alerts", inventory_alerts),
    ("Phase 5", "Power BI Dataset", powerbi_dataset),
)


def run_pipeline() -> None:
    """Run each existing module and stop immediately if any stage raises."""
    for phase, name, module in STAGES:
        print(f"[{phase}] {name}", flush=True)
        module.run()
        print("PASS", flush=True)
    print("Project pipeline completed successfully.", flush=True)


if __name__ == "__main__":
    run_pipeline()
