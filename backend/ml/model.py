"""
PU Bagging Classifier for Shadow Fleet detection.

Implements Positive-Unlabeled Learning using a bagging approach:
- For each bag: use all positives + random sample from unlabeled as pseudo-negatives
- Train a Random Forest per bag
- Average predictions across bags

This correctly handles the PU Learning setting where unlabeled != negative.
"""

import logging
from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.base import BaseEstimator, ClassifierMixin

logger = logging.getLogger(__name__)


class PUBaggingClassifier(BaseEstimator, ClassifierMixin):
    """
    Positive-Unlabeled Bagging Classifier.

    For each bag in the ensemble:
    1. Take ALL positive (confirmed shadow fleet) samples
    2. Sample len(positives) from unlabeled as pseudo-negatives
    3. Train a RandomForestClassifier on this balanced P vs sampled-U task
    4. Average predict_proba across all bags for final prediction

    Parameters
    ----------
    n_estimators : int
        Number of bagging iterations (default 50).
    n_trees_per_bag : int
        Number of trees in each Random Forest (default 100).
    max_depth : int or None
        Max tree depth per RF (default 10).
    random_state : int
        Random seed for reproducibility (default 42).
    """

    def __init__(
        self,
        n_estimators: int = 50,
        n_trees_per_bag: int = 100,
        max_depth: int | None = 10,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.n_trees_per_bag = n_trees_per_bag
        self.max_depth = max_depth
        self.random_state = random_state
        self.estimators_: list[RandomForestClassifier] = []
        self.feature_importances_array_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "PUBaggingClassifier":
        """
        Fit the PU Bagging ensemble.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        y : array-like of shape (n_samples,)
            Labels: 1 for positive (confirmed shadow fleet), 0 for unlabeled.
        """
        X = np.asarray(X)
        y = np.asarray(y)

        pos_idx = np.where(y == 1)[0]
        unl_idx = np.where(y == 0)[0]
        n_pos = len(pos_idx)

        if n_pos == 0:
            raise ValueError("No positive samples found (label=1)")
        if len(unl_idx) == 0:
            raise ValueError("No unlabeled samples found (label=0)")

        logger.info(
            "Fitting PU Bagging: %d bags, %d positives, %d unlabeled",
            self.n_estimators, n_pos, len(unl_idx),
        )

        rng = np.random.default_rng(self.random_state)
        self.estimators_ = []
        importances = []

        for i in range(self.n_estimators):
            # Sample pseudo-negatives from unlabeled
            sample_size = min(n_pos, len(unl_idx))
            neg_sample = rng.choice(unl_idx, size=sample_size, replace=False)

            # Combine positive + pseudo-negative
            bag_idx = np.concatenate([pos_idx, neg_sample])
            X_bag = X[bag_idx]
            y_bag = np.concatenate([
                np.ones(n_pos, dtype=int),
                np.zeros(sample_size, dtype=int),
            ])

            # Train RF on this bag
            rf = RandomForestClassifier(
                n_estimators=self.n_trees_per_bag,
                max_depth=self.max_depth,
                random_state=self.random_state + i,
                n_jobs=-1,
                class_weight="balanced",
            )
            rf.fit(X_bag, y_bag)
            self.estimators_.append(rf)
            importances.append(rf.feature_importances_)

            if (i + 1) % 10 == 0:
                logger.info("  Trained bag %d/%d", i + 1, self.n_estimators)

        self.feature_importances_array_ = np.array(importances)
        logger.info("PU Bagging training complete")
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Average predict_proba across all bags.

        Returns array of shape (n_samples, 2) with [P(unlabeled), P(shadow)].
        """
        X = np.asarray(X)
        probas = np.zeros((X.shape[0], 2))

        for rf in self.estimators_:
            probas += rf.predict_proba(X)

        probas /= len(self.estimators_)
        return probas

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Binary prediction using threshold on P(shadow)."""
        probas = self.predict_proba(X)
        return (probas[:, 1] >= threshold).astype(int)

    @property
    def feature_importances_(self) -> np.ndarray:
        """Average feature importances across all bags."""
        if self.feature_importances_array_ is None:
            raise ValueError("Model not fitted yet")
        return self.feature_importances_array_.mean(axis=0)
