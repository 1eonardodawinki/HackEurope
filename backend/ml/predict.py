"""
Prediction module for Shadow Fleet detection.

Loads a trained model and scores vessels. Designed as a drop-in bridge
for the existing ml_model.py placeholder.
"""

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .feature_engineering import engineer_features, FEATURE_COLUMNS

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"

# Module-level cache
_cached_artifact: Optional[dict] = None


def load_model(path: str | Path | None = None) -> dict:
    """
    Load model artifact from pickle.
    Default: models/latest.pkl
    Caches in module-level variable for repeated calls.
    """
    global _cached_artifact

    if path is None:
        path = MODELS_DIR / "latest.pkl"
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Model not found: {path}. Run the training pipeline first: "
            f"python -m ml.run_pipeline --step train"
        )

    if _cached_artifact is not None and _cached_artifact.get("_path") == str(path):
        return _cached_artifact

    logger.info("Loading model from %s", path)
    with open(path, "rb") as f:
        artifact = pickle.load(f)

    artifact["_path"] = str(path)
    _cached_artifact = artifact

    logger.info("Model loaded: %s", artifact["model_version"])
    return artifact


def _classify_risk_tier(probability: float) -> str:
    """Map probability to risk tier (matches ml_model.py thresholds)."""
    if probability > 0.70:
        return "HIGH"
    elif probability > 0.45:
        return "MEDIUM"
    return "LOW"


def score_vessel(
    mmsi: str,
    events: list[dict] | pd.DataFrame | None = None,
    vessel_name: str = "",
) -> dict:
    """
    Score a single vessel for shadow fleet probability.

    Parameters
    ----------
    mmsi : str
        MMSI number of the vessel.
    events : list[dict] or DataFrame or None
        Events for this vessel. If None, looks up in synthetic dataset.
    vessel_name : str
        Optional vessel name.

    Returns
    -------
    dict matching ml_model.py schema:
        mmsi, vessel_name, probability, risk_tier, model_version, feature_contributions
    """
    artifact = load_model()
    model = artifact["model"]
    feature_cols = artifact["feature_columns"]

    if events is None:
        # Try loading from synthetic data for demo
        try:
            from .data_loader import load_events
            all_events = load_events()
            events = all_events[all_events["mmsi"] == mmsi]
            if events.empty:
                logger.warning("No events found for MMSI %s, returning default score", mmsi)
                return {
                    "mmsi": mmsi,
                    "vessel_name": vessel_name,
                    "probability": 0.5,
                    "risk_tier": "MEDIUM",
                    "model_version": artifact["model_version"],
                    "note": "No event data available for this vessel",
                }
        except FileNotFoundError:
            logger.warning("No synthetic data available, returning default score")
            return {
                "mmsi": mmsi,
                "vessel_name": vessel_name,
                "probability": 0.5,
                "risk_tier": "MEDIUM",
                "model_version": artifact["model_version"],
                "note": "No training data or event data available",
            }
    elif isinstance(events, list):
        events = pd.DataFrame(events)

    if isinstance(events, pd.DataFrame) and not events.empty:
        # Ensure timestamps are parsed
        if events["turn_off"].dtype == object:
            events = events.copy()
            events["turn_off"] = pd.to_datetime(events["turn_off"])
            events["turn_on"] = pd.to_datetime(events["turn_on"])

        ship_features = engineer_features(events)
        if ship_features.empty:
            probability = 0.5
            contributions = {}
        else:
            X = ship_features[feature_cols].values
            probability = float(model.predict_proba(X)[:, 1][0])

            # Feature contributions (top features)
            importances = model.feature_importances_
            feature_values = X[0]
            contributions = {}
            sorted_idx = np.argsort(importances)[::-1][:5]
            for idx in sorted_idx:
                contributions[feature_cols[idx]] = {
                    "importance": round(float(importances[idx]), 4),
                    "value": round(float(feature_values[idx]), 4),
                }
    else:
        probability = 0.5
        contributions = {}

    probability = round(float(np.clip(probability, 0.0, 1.0)), 4)

    return {
        "mmsi": mmsi,
        "vessel_name": vessel_name,
        "probability": probability,
        "risk_tier": _classify_risk_tier(probability),
        "model_version": artifact["model_version"],
        "feature_contributions": contributions,
    }


def score_batch(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Score all ships in a DataFrame of events.
    Returns DataFrame with columns: mmsi, probability, risk_tier.
    """
    artifact = load_model()
    model = artifact["model"]
    feature_cols = artifact["feature_columns"]

    ship_features = engineer_features(events_df)

    X = ship_features[feature_cols].values
    probas = model.predict_proba(X)[:, 1]

    results = ship_features[["mmsi"]].copy()
    results["probability"] = np.round(probas, 4)
    results["risk_tier"] = results["probability"].apply(_classify_risk_tier)

    logger.info(
        "Scored %d ships: %d HIGH, %d MEDIUM, %d LOW",
        len(results),
        (results["risk_tier"] == "HIGH").sum(),
        (results["risk_tier"] == "MEDIUM").sum(),
        (results["risk_tier"] == "LOW").sum(),
    )

    return results
