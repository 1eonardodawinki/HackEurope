"""
Evaluation metrics and visualizations for Shadow Fleet detection model.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .data_loader import load_events
from .feature_engineering import engineer_features, FEATURE_COLUMNS

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent / "outputs"


def precision_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Among the top-k highest scored ships, what fraction are confirmed positives?"""
    if k > len(y_scores):
        k = len(y_scores)
    top_k_idx = np.argsort(y_scores)[::-1][:k]
    return float(y_true[top_k_idx].sum() / k)


def plot_feature_importances(
    importances: np.ndarray,
    feature_names: list[str],
    output_path: Path,
) -> None:
    """Horizontal bar chart of feature importances."""
    sorted_idx = np.argsort(importances)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(
        [feature_names[i] for i in sorted_idx],
        importances[sorted_idx],
        color="#2196F3",
    )
    ax.set_xlabel("Feature Importance")
    ax.set_title("Shadow Fleet Detection — Feature Importances")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("Saved feature importances plot to %s", output_path)


def plot_score_distribution(
    scores_positive: np.ndarray,
    scores_unlabeled: np.ndarray,
    output_path: Path,
) -> None:
    """Overlapping histograms of scores for positives vs. unlabeled."""
    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.linspace(0, 1, 50)
    ax.hist(scores_unlabeled, bins=bins, alpha=0.6, label="Unlabeled", color="#9E9E9E", density=True)
    ax.hist(scores_positive, bins=bins, alpha=0.7, label="Confirmed Shadow Fleet", color="#F44336", density=True)
    ax.set_xlabel("Risk Score")
    ax.set_ylabel("Density")
    ax.set_title("Score Distribution: Shadow Fleet vs. Unlabeled")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("Saved score distribution plot to %s", output_path)


def plot_precision_at_k_curve(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    output_path: Path,
) -> None:
    """Precision@k curve for various k values."""
    k_values = list(range(10, min(len(y_scores), 2001), 10))
    precisions = [precision_at_k(y_true, y_scores, k) for k in k_values]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(k_values, precisions, color="#4CAF50", linewidth=2)
    ax.set_xlabel("k (top-k ships)")
    ax.set_ylabel("Precision@k")
    ax.set_title("Precision@k Curve")
    ax.axhline(y=y_true.mean(), color="gray", linestyle="--", label=f"Random baseline ({y_true.mean():.3f})")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("Saved precision@k plot to %s", output_path)


def evaluate_model(
    model_artifact: dict,
    events_df: pd.DataFrame | None = None,
) -> dict:
    """
    Full evaluation of a trained model.

    Computes metrics, generates plots, saves everything to outputs/.
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    model = model_artifact["model"]
    feature_cols = model_artifact["feature_columns"]

    # Load data
    if events_df is None:
        events_df = load_events()

    ship_features = engineer_features(events_df)

    X = ship_features[feature_cols].values
    y = ship_features["label"].values

    # Score all ships
    scores = model.predict_proba(X)[:, 1]

    # Metrics
    p_at_100 = precision_at_k(y, scores, k=100)
    p_at_500 = precision_at_k(y, scores, k=500)
    p_at_1000 = precision_at_k(y, scores, k=min(1000, len(y)))

    # Risk tier distribution
    high = (scores > 0.70).sum()
    medium = ((scores > 0.45) & (scores <= 0.70)).sum()
    low = (scores <= 0.45).sum()

    metrics = {
        "precision_at_100": p_at_100,
        "precision_at_500": p_at_500,
        "precision_at_1000": p_at_1000,
        "total_ships": len(y),
        "confirmed_positive": int(y.sum()),
        "unlabeled": int((y == 0).sum()),
        "risk_tier_distribution": {
            "HIGH": int(high),
            "MEDIUM": int(medium),
            "LOW": int(low),
        },
        "score_stats": {
            "mean": float(scores.mean()),
            "std": float(scores.std()),
            "min": float(scores.min()),
            "max": float(scores.max()),
            "median": float(np.median(scores)),
        },
        "model_version": model_artifact["model_version"],
    }

    logger.info("Precision@100: %.3f", p_at_100)
    logger.info("Precision@500: %.3f", p_at_500)
    logger.info("Precision@1000: %.3f", p_at_1000)
    logger.info("Risk tiers: HIGH=%d, MEDIUM=%d, LOW=%d", high, medium, low)

    # Feature importances
    importances = model.feature_importances_
    importance_ranking = sorted(
        zip(feature_cols, importances),
        key=lambda x: x[1],
        reverse=True,
    )
    metrics["feature_importance_ranking"] = [
        {"feature": name, "importance": round(float(imp), 4)}
        for name, imp in importance_ranking
    ]
    logger.info("Top 5 features:")
    for name, imp in importance_ranking[:5]:
        logger.info("  %s: %.4f", name, imp)

    # Plots
    plot_feature_importances(
        importances, feature_cols,
        OUTPUTS_DIR / "feature_importances.png",
    )

    scores_pos = scores[y == 1]
    scores_unl = scores[y == 0]
    plot_score_distribution(
        scores_pos, scores_unl,
        OUTPUTS_DIR / "score_distribution.png",
    )

    plot_precision_at_k_curve(
        y, scores,
        OUTPUTS_DIR / "precision_at_k.png",
    )

    # Save metrics JSON
    metrics_path = OUTPUTS_DIR / "evaluation_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Saved metrics to %s", metrics_path)

    return metrics
