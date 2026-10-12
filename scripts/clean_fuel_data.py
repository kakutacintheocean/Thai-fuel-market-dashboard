"""
Thai Fuel Market Pipeline: raw data.go.th / EPPO / DOEB extracts turned into one clean fact table.

Run:
    python clean_fuel_data.py

Inputs (raw, dirty, left untouched):
    data/raw/dataset_11_15.csv                         (EPPO: การใช้น้ำมันสำเร็จรูป, monthly, by product, ค.ศ., Million Litres)
    data/raw/vw_opendata_039_e_fuel_sum_data_view.csv   (DOEB: การส่งออกน้ำมันสำเร็จรูป, monthly, total, พ.ศ., thousand litres)

Output (clean, one table, two formats so it's usable from Excel/Power BI or SQL alike):
    data/processed/fact_fuel_monthly.csv
    data/processed/fuel_market.db   (table: fact_fuel_monthly)

Glossary (used throughout sql/analysis_queries.sql and the dashboard):
    MoM (Month-over-Month): this month's value vs. the immediately previous month.
    YoY (Year-over-Year):   this month's value vs. the same month one year earlier.
"""

import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

CONSUMPTION_FILE = RAW_DIR / "dataset_11_15.csv"
EXPORT_FILE = RAW_DIR / "vw_opendata_039_e_fuel_sum_data_view.csv"

OUT_CSV = PROCESSED_DIR / "fact_fuel_monthly.csv"
OUT_DB = PROCESSED_DIR / "fuel_market.db"

MONTH_NAME_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Raw file spells products in ALL CAPS and inconsistently with how an energy-company
# analyst would normally label them in a report. Map to the canonical names used
# throughout the rest of the pipeline (SQL / Power BI) so every downstream join works
# on the same string.
PRODUCT_NAME_MAP = {
    "DIESEL": "Diesel",
    "GASOLINE": "Gasoline",
    "FUEL OIL": "Fuel Oil",
    "JET PETROLEUM": "Jet Fuel",
    "KEROSENE": "Kerosene",
    "LPG": "LPG",
}

BUDDHIST_YEAR_OFFSET = 543


def clean_consumption(path: Path) -> tuple[pd.DataFrame, dict]:
    """EPPO dataset_11_15.csv: Year,Month,Product,Quantity,UNIT (already Gregorian,
    already Million Litres, but Month is a spelled-out name and Product is ALL CAPS)."""
    stats = {"rows_in": 0, "rows_dropped_bad_month": 0, "rows_dropped_invalid_qty": 0, "duplicates_dropped": 0}

    df = pd.read_csv(path, encoding="utf-8-sig")
    stats["rows_in"] = len(df)

    df["month_key"] = df["Month"].str.strip().str.lower()
    bad_month = ~df["month_key"].isin(MONTH_NAME_TO_NUM)
    stats["rows_dropped_bad_month"] = int(bad_month.sum())
    df = df[~bad_month].copy()

    df["year"] = df["Year"].astype(int)
    df["month"] = df["month_key"].map(MONTH_NAME_TO_NUM).astype(int)

    df["product"] = df["Product"].str.strip().str.upper().map(PRODUCT_NAME_MAP)
    unmapped = df["product"].isna()
    if unmapped.any():
        # A product spelling the map doesn't recognize yet: keep it visible
        # instead of silently dropping real volume.
        df.loc[unmapped, "product"] = df.loc[unmapped, "Product"].str.strip().str.title()

    df["quantity_million_litres"] = pd.to_numeric(df["Quantity"], errors="coerce")
    bad_qty = df["quantity_million_litres"].isna() | (df["quantity_million_litres"] < 0)
    stats["rows_dropped_invalid_qty"] = int(bad_qty.sum())
    df = df[~bad_qty].copy()

    df["record_date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    df["metric_type"] = "Consumption"
    df["source_file"] = path.name

    out = df[["record_date", "year", "month", "product", "metric_type", "quantity_million_litres", "source_file"]]
    before = len(out)
    out = out.drop_duplicates(subset=["record_date", "product", "metric_type"])
    stats["duplicates_dropped"] = before - len(out)

    return out, stats


def clean_export(path: Path) -> tuple[pd.DataFrame, dict]:
    """DOEB vw_opendata_039_e_fuel_sum_data_view.csv: SUBJECT,YEAR_ID,MONTH_ID,QTY,UNIT,DATAOWNER
    (YEAR_ID is Buddhist Era, QTY is thousand litres/month, no product breakdown, total only)."""
    stats = {"rows_in": 0, "rows_dropped_invalid_month": 0, "rows_dropped_invalid_qty": 0, "duplicates_dropped": 0}

    df = pd.read_csv(path, encoding="utf-8-sig")
    stats["rows_in"] = len(df)

    df["year"] = df["YEAR_ID"].astype(int) - BUDDHIST_YEAR_OFFSET
    df["month"] = pd.to_numeric(df["MONTH_ID"], errors="coerce")
    bad_month = df["month"].isna() | (df["month"] < 1) | (df["month"] > 12)
    stats["rows_dropped_invalid_month"] = int(bad_month.sum())
    df = df[~bad_month].copy()
    df["month"] = df["month"].astype(int)

    # UNIT column says "พันลิตรต่อเดือน" (thousand litres/month), while the consumption
    # table is in million litres, so this must be divided by 1,000 to join cleanly.
    qty_thousand_litres = pd.to_numeric(df["QTY"], errors="coerce")
    bad_qty = qty_thousand_litres.isna() | (qty_thousand_litres < 0)
    stats["rows_dropped_invalid_qty"] = int(bad_qty.sum())
    df = df[~bad_qty].copy()
    df["quantity_million_litres"] = qty_thousand_litres[~bad_qty] / 1000.0

    df["record_date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    df["product"] = "All Products"
    df["metric_type"] = "Export"
    df["source_file"] = path.name

    out = df[["record_date", "year", "month", "product", "metric_type", "quantity_million_litres", "source_file"]]
    before = len(out)
    out = out.drop_duplicates(subset=["record_date", "product", "metric_type"])
    stats["duplicates_dropped"] = before - len(out)

    return out, stats


def main() -> None:
    start = time.perf_counter()

    for required in (CONSUMPTION_FILE, EXPORT_FILE):
        if not required.exists():
            sys.exit(f"Missing raw file: {required}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    consumption_df, consumption_stats = clean_consumption(CONSUMPTION_FILE)
    export_df, export_stats = clean_export(EXPORT_FILE)

    fact = pd.concat([consumption_df, export_df], ignore_index=True)
    fact = fact.sort_values(["record_date", "metric_type", "product"]).reset_index(drop=True)
    fact["record_date"] = fact["record_date"].dt.strftime("%Y-%m-%d")

    fact.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    with sqlite3.connect(OUT_DB) as conn:
        fact.to_sql("fact_fuel_monthly", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_fuel_monthly(record_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_product ON fact_fuel_monthly(product, metric_type)")

    elapsed = time.perf_counter() - start

    print("=" * 60)
    print("Thai Fuel Market pipeline: run summary")
    print("=" * 60)
    print(f"Consumption (EPPO) : {consumption_stats['rows_in']} rows in -> "
          f"{len(consumption_df)} rows out "
          f"(dropped: bad_month={consumption_stats['rows_dropped_bad_month']}, "
          f"bad_qty={consumption_stats['rows_dropped_invalid_qty']}, "
          f"dupes={consumption_stats['duplicates_dropped']})")
    print(f"Export (DOEB)       : {export_stats['rows_in']} rows in -> "
          f"{len(export_df)} rows out "
          f"(dropped: bad_month={export_stats['rows_dropped_invalid_month']}, "
          f"bad_qty={export_stats['rows_dropped_invalid_qty']}, "
          f"dupes={export_stats['duplicates_dropped']})")
    print(f"Final table          : {len(fact)} rows -> {OUT_CSV.name}, {OUT_DB.name} (table fact_fuel_monthly)")
    print(f"Date range            : {fact['record_date'].min()} .. {fact['record_date'].max()}")
    print(f"Elapsed time          : {elapsed:.3f} sec")
    print("=" * 60)


if __name__ == "__main__":
    main()
