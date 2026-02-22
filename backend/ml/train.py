"""
Training pipeline for Shadow Fleet detection model.

Uses GroupKFold to ensure ships in test never appear in training.
Saves trained model as pickle.
"""

import logging
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from .data_loader import load_events
from .feature_engineering import engineer_features, FEATURE_COLUMNS
from .model import PUBaggingClassifier

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"


def precision_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Among the top-k highest scored ships, what fraction are confirmed positives?"""
    if k > len(y_scores):
        k = len(y_scores)
    top_k_idx = np.argsort(y_scores)[::-1][:k]
    return float(y_true[top_k_idx].sum() / k)


def train(
    events_df: pd.DataFrame | None = None,
    n_splits: int = 5,
    n_estimators: int = 50,
    save: bool = True,
) -> dict:
    """
    Full training pipeline.

    1. Load data (or use provided DataFrame)
    2. Engineer features
    3. Cross-validate with GroupKFold by MMSI
    4. Train final model on all data
    5. Save model artifact

    Returns dict with training metrics.
    """
    # Load and prepare data
    if events_df is None:
        events_df = load_events()

    ship_features = engineer_features(events_df)

    X = ship_features[FEATURE_COLUMNS].values
    y = ship_features["label"].values
    groups = ship_features["mmsi"].values

    n_positive = (y == 1).sum()
    n_unlabeled = (y == 0).sum()
    logger.info("Training data: %d ships (%d positive, %d unlabeled)", len(y), n_positive, n_unlabeled)

    # Cross-validation with GroupKFold
    gkf = GroupKFold(n_splits=n_splits)
    fold_metrics = []

    for fold_i, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Only evaluate if test fold has positives
        n_test_pos = y_test.sum()
        if n_test_pos == 0:
            logger.warning("Fold %d has no positives in test set, skipping", fold_i)
            continue

        model = PUBaggingClassifier(
            n_estimators=n_estimators,
            n_trees_per_bag=100,
            max_depth=10,
            random_state=42 + fold_i,
        )
        model.fit(X_train, y_train)

        scores = model.predict_proba(X_test)[:, 1]

        p_at_100 = precision_at_k(y_test, scores, k=min(100, len(y_test)))
        p_at_500 = precision_at_k(y_test, scores, k=min(500, len(y_test)))

        fold_metrics.append({
            "fold": fold_i,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "n_test_positive": int(n_test_pos),
            "precision_at_100": p_at_100,
            "precision_at_500": p_at_500,
        })

        logger.info(
            "  Fold %d: P@100=%.3f, P@500=%.3f (test: %d ships, %d positive)",
            fold_i, p_at_100, p_at_500, len(test_idx), n_test_pos,
        )

    # Aggregate CV metrics
    if fold_metrics:
        mean_p100 = np.mean([m["precision_at_100"] for m in fold_metrics])
        mean_p500 = np.mean([m["precision_at_500"] for m in fold_metrics])
        logger.info("CV Results: mean P@100=%.3f, mean P@500=%.3f", mean_p100, mean_p500)
    else:
        mean_p100 = mean_p500 = 0.0
        logger.warning("No valid folds for evaluation")

    # Train final model on ALL data
    logger.info("Training final model on all %d ships...", len(y))
    final_model = PUBaggingClassifier(
        n_estimators=n_estimators,
        n_trees_per_bag=100,
        max_depth=10,
        random_state=42,
    )
    final_model.fit(X, y)

    # Prepare artifact
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_version = f"shadow-fleet-v1.0-{timestamp}"

    artifact = {
        "model": final_model,
        "feature_columns": FEATURE_COLUMNS,
        "model_version": model_version,
        "training_metrics": {
            "n_ships": len(y),
            "n_positive": int(n_positive),
            "n_unlabeled": int(n_unlabeled),
            "n_features": len(FEATURE_COLUMNS),
            "n_estimators": n_estimators,
            "cv_mean_precision_at_100": mean_p100,
            "cv_mean_precision_at_500": mean_p500,
            "fold_details": fold_metrics,
        },
        "trained_at": datetime.now().isoformat(),
    }

    # Save
    if save:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        model_path = MODELS_DIR / f"shadow_fleet_model_{timestamp}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(artifact, f)
        logger.info("Saved model to %s", model_path)

        latest_path = MODELS_DIR / "latest.pkl"
        with open(latest_path, "wb") as f:
            pickle.dump(artifact, f)
        logger.info("Saved latest model to %s", latest_path)

        artifact["model_path"] = str(model_path)

    return artifact
