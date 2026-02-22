#!/usr/bin/env python3
"""
Merge Vessel_Data CSVs into a single SQLite table.

- Renames `ssvid` to `mmsi`
- Ensures each column appears only once in the final schema
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sqlite3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge vessel CSVs into one SQLite database/table."
    )
    parser.add_argument(
        "--input-glob",
        default="Vessel_Data/*.csv",
        help="Glob pattern for source CSV files.",
    )
    parser.add_argument(
        "--output-db",
        default="backend/vessel_data.db",
        help="Output SQLite file path.",
    )
    parser.add_argument(
        "--table-name",
        default="vessel_data",
        help="Destination table name.",
    )
    return parser.parse_args()


def normalize_col(name: str) -> str:
    return "mmsi" if name == "ssvid" else name


def discover_files(pattern: str) -> list[str]:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matched pattern: {pattern}")
    return files


def get_header(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return [normalize_col(c) for c in next(reader)]


def ordered_unique_columns(files: list[str]) -> list[str]:
    seen: set[str] = set()
    cols: list[str] = []
    for path in files:
        for col in get_header(path):
            if col not in seen:
                cols.append(col)
                seen.add(col)
    return cols


def create_table(conn: sqlite3.Connection, table_name: str, columns: list[str]) -> None:
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
    conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
    if "mmsi" in columns:
        conn.execute(f'CREATE INDEX "idx_{table_name}_mmsi" ON "{table_name}" ("mmsi")')
    if "vessel_record_id" in columns:
        conn.execute(
            f'CREATE INDEX "idx_{table_name}_record_id" ON "{table_name}" ("vessel_record_id")'
        )


def merge_to_sqlite(files: list[str], output_db: str, table_name: str) -> int:
    columns = ordered_unique_columns(files)
    os.makedirs(os.path.dirname(output_db) or ".", exist_ok=True)
    conn = sqlite3.connect(output_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    create_table(conn, table_name, columns)

    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f'INSERT INTO "{table_name}" ({", ".join(f"""\"{c}\"""" for c in columns)}) '
        f"VALUES ({placeholders})"
    )

    total_rows = 0
    batch: list[tuple[str | None, ...]] = []
    batch_size = 10000

    for path in files:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                norm = {normalize_col(k): v for k, v in row.items()}
                batch.append(tuple(norm.get(c) for c in columns))
                total_rows += 1
                if len(batch) >= batch_size:
                    conn.executemany(insert_sql, batch)
                    conn.commit()
                    batch.clear()

    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    conn.close()
    return total_rows


def main() -> None:
    args = parse_args()
    files = discover_files(args.input_glob)
    cols = ordered_unique_columns(files)
    rows = merge_to_sqlite(files, args.output_db, args.table_name)
    print(f"input_files={len(files)}")
    print(f"output_db={args.output_db}")
    print(f"table={args.table_name}")
    print(f"columns={len(cols)}")
    print("column_names=" + ",".join(cols))
    print(f"rows_inserted={rows}")


if __name__ == "__main__":
    main()
