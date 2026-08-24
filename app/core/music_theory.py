"""
Music theory constants and helpers for dance style classification.

Defines tempo ranges for Swedish folk dance styles.

AGPL-3.0 License - See LICENSE file for details.
"""

# Tempo ranges per style - defines what's "typical" for each dance
# Format: "Style": (slow_threshold, typical_low, typical_high, fast_threshold)
TEMPO_RANGES = {
    #                 Slow   Typical Range    Fast
    "Hambo":        (95,    100,    115,    125),
    "Polska":       (100,   105,    125,    135),
    "Slängpolska":  (105,   110,    125,    135),
    "Vals":         (140,   150,    200,    220),
    "Schottis":     (130,   140,    160,    175),
    "Snoa":         (70,    80,     110,    120),
    "Polka":        (110,   120,    150,    165),
    "Engelska":     (100,   110,    130,    145),
    "Mazurka":      (120,   130,    160,    175),
    "Gånglåt":      (70,    80,     100,    110),
}

def get_tempo_description(style: str, bpm: int) -> dict:
    """
    Returns tempo info relative to what's typical for the dance style.

    Returns: {
        "level": 1-5 (for filtering/sorting),
        "label": "Långsamt" / "Lugnt" / "Lagom" / "Snabbt" / "Väldigt snabbt",
        "relative": "slower" / "typical" / "faster" (vs typical for this style)
    }
    """
    if not style or style not in TEMPO_RANGES or not bpm:
        return {
            "level": 3,
            "label": "Lagom",
            "relative": "typical"
        }

    slow_th, typical_low, typical_high, fast_th = TEMPO_RANGES[style]

    # 5 tempo levels with Swedish labels
    if bpm < slow_th:
        return {"level": 1, "label": "Långsamt", "relative": "slower"}
    elif bpm < typical_low:
        return {"level": 2, "label": "Lugnt", "relative": "slower"}
    elif bpm <= typical_high:
        return {"level": 3, "label": "Lagom", "relative": "typical"}
    elif bpm <= fast_th:
        return {"level": 4, "label": "Snabbt", "relative": "faster"}
    else:
        return {"level": 5, "label": "Väldigt snabbt", "relative": "faster"}


def categorize_tempo(style: str, bpm: int) -> str:
    """
    Returns simple category string for backwards compatibility.
    """
    tempo = get_tempo_description(style, bpm)
    return tempo["label"]
