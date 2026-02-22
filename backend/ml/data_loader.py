"""
Data loading and validation for Shadow Fleet ML pipeline.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

EXPECTED_COLUMNS = [
    "mmsi", "event_id", "flag", "nearest_ais_km", "unmatched",
    "vessel_class", "size_category", "speed_knots", "heading",
    "turn_off", "turn_on", "lat", "lon", "label",
]

DTYPES = {
    "mmsi": str,
    "event_id": int,
    "flag": str,
    "nearest_ais_km": float,
    "unmatched": bool,
    "vessel_class": str,
    "size_category": str,
    "speed_knots": float,
    "heading": float,
    "lat": float,
    "lon": float,
    "label": int,
}


def validate_schema(df: pd.DataFrame) -> None:
    """Validate DataFrame has all expected columns. Raises ValueError on failure."""
    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    extra = set(df.columns) - set(EXPECTED_COLUMNS)
    if extra:
        logger.warning("Extra columns found (will be ignored): %s", extra)


def load_events(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load event data from CSV or Parquet.

    Auto-detects format from file extension.
    Validates schema, parses timestamps, handles missing values.
    """
    if path is None:
        path = DATA_DIR / "synthetic_events.csv"
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    logger.info("Loading events from %s", path)

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, dtype={"mmsi": str})

    validate_schema(df)

    # Ensure MMSI is string
    df["mmsi"] = df["mmsi"].astype(str)

    # Parse timestamps
    df["turn_off"] = pd.to_datetime(df["turn_off"], format="ISO8601")
    df["turn_on"] = pd.to_datetime(df["turn_on"], format="ISO8601")

    # Handle missing values
    df["nearest_ais_km"] = df["nearest_ais_km"].fillna(df["nearest_ais_km"].median())
    df["speed_knots"] = df["speed_knots"].fillna(df["speed_knots"].median())
    df["heading"] = df["heading"].fillna(0.0)
    df["unmatched"] = df["unmatched"].fillna(False).astype(bool)

    logger.info(
        "Loaded %d events for %d unique ships (%d labeled positive)",
        len(df),
        df["mmsi"].nunique(),
        df[df["label"] == 1]["mmsi"].nunique(),
    )

    return df


def load_shadow_fleet_list(path: str | Path | None = None) -> set[str]:
    """Load the set of confirmed shadow fleet MMSIs."""
    if path is None:
        path = DATA_DIR / "shadow_fleet_mmsis.csv"
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Shadow fleet list not found: {path}")

    df = pd.read_csv(path, dtype={"mmsi": str})
    mmsis = set(df["mmsi"].astype(str))
    logger.info("Loaded %d confirmed shadow fleet MMSIs", len(mmsis))
    return mmsis
