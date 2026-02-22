#!/usr/bin/env python3
"""
Merge all Historical_Data CSV files into one SQLite DB while keeping only rows
where matched_category is 'unmatched'.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sqlite3
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge historical CSV files into a filtered SQLite database."
    )
    parser.add_argument(
        "--input-glob",
        default="Historical_Data/*.csv",
        help="Glob pattern for input CSV files.",
    )
    parser.add_argument(
        "--output-db",
        default="backend/historical_unmatched.db",
        help="Path to output SQLite database.",
    )
    parser.add_argument(
        "--table-name",
        default="historical_detections",
        help="Destination table name.",
    )
    return parser.parse_args()


def normalize(value: str) -> str:
    return value.strip().lower()


def files_from_glob(pattern: str) -> list[str]:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files matched: {pattern}")
    return files


def create_table(conn: sqlite3.Connection, table_name: str) -> None:
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    conn.execute(
        f'''
        CREATE TABLE "{table_name}" (
            scene_id TEXT,
            timestamp TEXT,
            lat REAL,
            lon REAL,
            presence_score REAL,
            length_m REAL,
            mmsi TEXT,
            matching_score REAL,
            fishing_score REAL,
            matched_category TEXT
        )
        '''
    )
    conn.execute(
        f'CREATE INDEX "idx_{table_name}_timestamp" ON "{table_name}" (timestamp)'
    )
    conn.execute(f'CREATE INDEX "idx_{table_name}_mmsi" ON "{table_name}" (mmsi)')


def rows_from_csv(path: str) -> Iterable[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def merge_csvs(files: list[str], output_db: str, table_name: str) -> tuple[int, int]:
    os.makedirs(os.path.dirname(output_db) or ".", exist_ok=True)
    conn = sqlite3.connect(output_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")

    create_table(conn, table_name)

    insert_sql = f'''
        INSERT INTO "{table_name}" (
            scene_id, timestamp, lat, lon, presence_score, length_m,
            mmsi, matching_score, fishing_score, matched_category
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''

    kept = 0
    dropped = 0
    batch: list[tuple[object, ...]] = []
    batch_size = 10000

    for csv_file in files:
        for row in rows_from_csv(csv_file):
            if normalize(row.get("matched_category", "")) != "unmatched":
                dropped += 1
                continue

            batch.append(
                (
                    row.get("scene_id"),
                    row.get("timestamp"),
                    float(row["lat"]) if row.get("lat") else None,
                    float(row["lon"]) if row.get("lon") else None,
                    float(row["presence_score"]) if row.get("presence_score") else None,
                    float(row["length_m"]) if row.get("length_m") else None,
                    row.get("mmsi"),
                    float(row["matching_score"]) if row.get("matching_score") else None,
                    float(row["fishing_score"]) if row.get("fishing_score") else None,
                    row.get("matched_category"),
                )
            )
            kept += 1

            if len(batch) >= batch_size:
                conn.executemany(insert_sql, batch)
                conn.commit()
                batch.clear()

    if batch:
        conn.executemany(insert_sql, batch)
        conn.commit()

    conn.close()
    return kept, dropped


def main() -> None:
    args = parse_args()
    files = files_from_glob(args.input_glob)
    kept, dropped = merge_csvs(files, args.output_db, args.table_name)
    print(f"input_files={len(files)}")
    print(f"rows_kept={kept}")
    print(f"rows_dropped={dropped}")
    print(f"output_db={args.output_db}")
    print(f"table={args.table_name}")


if __name__ == "__main__":
    main()
