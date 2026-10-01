"""Turn Jev's answers into a next step.

Rules are checked top to bottom; the first match wins. Edit the thresholds
or the order below to change routing — nothing else needs to change.
"""

from dataclasses import dataclass

# Below this, we don't trust the team routing enough to act on it automatically.
TEAM_CONFIDENCE_FLOOR = 0.5

# Score runs 0..3 (see questions.URGENCY_LEVELS); 2.0+ means "Significant" or higher.
URGENT_SCORE_FLOOR = 2.0

# Noul probability that the customer wants money back.
REFUND_PROBABILITY_FLOOR = 0.5


@dataclass
class JevAnswers:
    team: str
    team_confidence: float
    wants_refund: float
    urgency_score: float
    urgency_confidence: float


def next_step(answers: JevAnswers) -> str:
    if answers.team_confidence < TEAM_CONFIDENCE_FLOOR:
        return "needs a person"
    if answers.urgency_score >= URGENT_SCORE_FLOOR:
        return "urgent"
    if answers.wants_refund >= REFUND_PROBABILITY_FLOOR:
        return "billing queue"
    return f"{answers.team} queue"
