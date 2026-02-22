"""
Shadow Fleet Detection ML Pipeline — CLI Runner.

Usage:
    cd backend
    python -m ml.run_pipeline                  # full pipeline
    python -m ml.run_pipeline --step generate  # only generate data
    python -m ml.run_pipeline --step train     # only train (data must exist)
    python -m ml.run_pipeline --step evaluate  # only evaluate (model must exist)
"""

import argparse
import logging
import sys
import time


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow Fleet Detection ML Pipeline")
    parser.add_argument(
        "--step",
        choices=["generate", "train", "evaluate", "all"],
        default="all",
        help="Pipeline step to run (default: all)",
    )
    parser.add_argument("--n-shadow", type=int, default=1300, help="Number of shadow fleet ships")
    parser.add_argument("--n-unlabeled", type=int, default=8000, help="Number of unlabeled ships")
    parser.add_argument("--n-estimators", type=int, default=50, help="PU bagging estimators")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("ml.pipeline")

    total_start = time.time()

    # Step 1: Generate synthetic data
    if args.step in ("generate", "all"):
        logger.info("=" * 60)
        logger.info("STEP 1: Generating synthetic data")
        logger.info("=" * 60)
        start = time.time()

        from .generate_synthetic_data import main as generate
        events_path = generate(n_shadow=args.n_shadow, n_unlabeled=args.n_unlabeled)
        logger.info("Data generation completed in %.1fs", time.time() - start)
        logger.info("")

    # Step 2: Train model
    if args.step in ("train", "all"):
        logger.info("=" * 60)
        logger.info("STEP 2: Training PU Learning model")
        logger.info("=" * 60)
        start = time.time()

        from .train import train
        artifact = train(n_estimators=args.n_estimators)
        logger.info("Training completed in %.1fs", time.time() - start)
        if "model_path" in artifact:
            logger.info("Model saved: %s", artifact["model_path"])
        logger.info("")

    # Step 3: Evaluate
    if args.step in ("evaluate", "all"):
        logger.info("=" * 60)
        logger.info("STEP 3: Evaluating model")
        logger.info("=" * 60)
        start = time.time()

        from .evaluate import evaluate_model
        from .predict import load_model
        artifact = load_model()
        results = evaluate_model(artifact)

        logger.info("")
        logger.info("RESULTS SUMMARY")
        logger.info("-" * 40)
        logger.info("Precision@100:  %.1f%%", results["precision_at_100"] * 100)
        logger.info("Precision@500:  %.1f%%", results["precision_at_500"] * 100)
        logger.info("Precision@1000: %.1f%%", results["precision_at_1000"] * 100)
        logger.info("")
        logger.info("Risk Distribution:")
        for tier, count in results["risk_tier_distribution"].items():
            logger.info("  %s: %d ships", tier, count)
        logger.info("")
        logger.info("Top 5 Features:")
        for feat in results["feature_importance_ranking"][:5]:
            logger.info("  %s: %.4f", feat["feature"], feat["importance"])
        logger.info("")
        logger.info("Evaluation completed in %.1fs", time.time() - start)

    total_elapsed = time.time() - total_start
    logger.info("")
    logger.info("Pipeline completed in %.1fs", total_elapsed)


if __name__ == "__main__":
    main()
