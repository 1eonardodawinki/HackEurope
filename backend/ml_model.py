"""
ML Model — dark fleet probability prediction.

This is a PLACEHOLDER. Replace get_dark_fleet_probability() with the actual
ML model when it is ready. The function signature and return schema must remain
stable so the rest of the pipeline does not need to change.
"""


async def get_dark_fleet_probability(mmsi: str, vessel_name: str = "") -> dict:
    """
    Predict the probability that a vessel is operating as part of a shadow/dark fleet.

    Args:
        mmsi: Maritime Mobile Service Identity number (9 digits)
        vessel_name: Optional vessel name for context

    Returns:
        dict with keys: mmsi, probability (0.0-1.0), risk_tier, model_version
    """
    # Deterministic seed from MMSI digits — demo gives consistent results per vessel
    seed = sum(int(c) for c in mmsi if c.isdigit()) if any(c.isdigit() for c in mmsi) else 50
    prob = round(0.35 + (seed % 60) / 100, 2)   # range: 0.35 – 0.94

    if prob > 0.70:
        tier = "HIGH"
    elif prob > 0.45:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return {
        "mmsi": mmsi,
        "vessel_name": vessel_name,
        "probability": prob,
        "risk_tier": tier,
        "model_version": "placeholder-v0.1",
        "note": "Placeholder — replace internals with trained model. Schema is stable.",
    }
