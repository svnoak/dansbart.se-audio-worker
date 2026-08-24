"""
Dance movement feedback manager.

Tracks crowd wisdom about how different dance styles feel.
Used for movement-based recommendations.

AGPL-3.0 License - See LICENSE file for details.
"""
from sqlalchemy.orm import Session
from app.core.models import DanceMovementFeedback


class MovementManager:
    """
    Manages crowd-sourced dance movement feedback.

    Stores and retrieves consensus about how dance styles feel
    (e.g., "Hambo feels sviktande and gungande").
    """

    # Seed data for cold start
    SEEDS = {
        "Hambo": ["Sviktande", "Gungande", "Tungt"],
        "Schottis": ["Sviktande", "Drivande", "Kantig"],
        "Snoa": ["Platt", "Drivande", "Jämn"],
        "Vals": ["Flytande", "Lätt", "Mjuk"],
        "Polka": ["Studsigt", "Drivande", "Snabbt"],
        "Slängpolska": ["Flytande", "Jämn", "Oändlig"],
        "Polska": ["Tungt", "Hängande", "Mustigt"]
    }

    def __init__(self, db: Session):
        self.db = db

    def get_feel_profile(self, dance_style: str) -> list[dict]:
        """
        Get the current crowd wisdom for a dance style.

        Returns: [{"tag": "Sviktande", "percent": 85, "is_dominant": True}, ...]
        """
        records = self.db.query(DanceMovementFeedback).filter(
            DanceMovementFeedback.dance_style == dance_style
        ).order_by(DanceMovementFeedback.score.desc()).all()

        total_votes = sum(r.occurrences for r in records)

        # Cold start: mix in seeds if not enough data
        if total_votes < 5:
            return self._mix_seeds_with_data(dance_style, records)

        return [
            {
                "tag": r.movement_tag,
                "percent": int((r.score / total_votes) * 100),
                "is_dominant": (r.score / total_votes) > 0.4
            }
            for r in records
        ]

    def register_feedback(self, dance_style: str, selected_tags: list[str]):
        """
        Register user feedback about a dance style's feel.
        """
        for tag in selected_tags:
            record = self.db.query(DanceMovementFeedback).filter(
                DanceMovementFeedback.dance_style == dance_style,
                DanceMovementFeedback.movement_tag == tag
            ).first()

            if not record:
                record = DanceMovementFeedback(
                    dance_style=dance_style,
                    movement_tag=tag,
                    score=0,
                    occurrences=0
                )
                self.db.add(record)

            record.score += 1.0
            record.occurrences += 1

        self.db.commit()

    def _mix_seeds_with_data(self, style, records):
        """Return hardcoded seeds if database is cold."""
        defaults = self.SEEDS.get(style, ["Odefinierad"])
        db_data = {r.movement_tag: r.score for r in records}

        result = []
        for tag in defaults:
            score = db_data.get(tag, 10.0)
            result.append({"tag": tag, "percent": 0, "status": "seed"})

        return result
