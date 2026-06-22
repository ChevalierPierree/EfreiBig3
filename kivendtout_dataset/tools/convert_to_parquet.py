#!/usr/bin/env python3
"""Convert KiVendTout CSV/JSONL to Parquet for MinIO + Parquet lakehouse.

Usage:
  python tools/convert_to_parquet.py --data-dir ./kivendtout_dataset

It tries DuckDB first (recommended), then pyarrow.
"""
import argparse, os, sys
import pandas as pd

def convert_with_duckdb(data_dir: str) -> bool:
    try:
        import duckdb
    except Exception:
        return False
    con = duckdb.connect()
    # Events: JSONL
    events_jsonl = os.path.join(data_dir, "events.jsonl")
    if os.path.exists(events_jsonl):
        con.execute(f"CREATE TABLE events AS SELECT * FROM read_json_auto('{events_jsonl}');")
        con.execute(f"COPY events TO '{os.path.join(data_dir,'events.parquet')}' (FORMAT 'parquet');")
    # CSV tables
    for name in ["customers","products","sessions","payments","orders","order_items","fraud_alerts"]:
        path = os.path.join(data_dir, f"{name}.csv")
        if os.path.exists(path):
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto('{path}', HEADER=true);")
            con.execute(f"COPY {name} TO '{os.path.join(data_dir,f'{name}.parquet')}' (FORMAT 'parquet');")
    return True

def convert_with_pyarrow(data_dir: str) -> bool:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        return False
    # Events JSONL -> Parquet
    events_jsonl = os.path.join(data_dir, "events.jsonl")
    if os.path.exists(events_jsonl):
        df = pd.read_json(events_jsonl, lines=True)
        table = pa.Table.from_pandas(df)
        pq.write_table(table, os.path.join(data_dir, "events.parquet"))
    # CSV -> Parquet
    for name in ["customers","products","sessions","payments","orders","order_items","fraud_alerts"]:
        path = os.path.join(data_dir, f"{name}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            table = pa.Table.from_pandas(df)
            pq.write_table(table, os.path.join(data_dir, f"{name}.parquet"))
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".", help="Path to kivendtout_dataset folder")
    args = ap.parse_args()
    data_dir = args.data_dir

    ok = convert_with_duckdb(data_dir)
    if ok:
        print("✅ Parquet generated with DuckDB")
        return
    ok = convert_with_pyarrow(data_dir)
    if ok:
        print("✅ Parquet generated with pyarrow")
        return

    print("❌ Could not generate Parquet: install duckdb or pyarrow.")
    print("   pip install duckdb  (recommended)\n   or\n   pip install pyarrow")
    sys.exit(1)

if __name__ == "__main__":
    main()
