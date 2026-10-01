"""Ask Jev the three triage questions for one message."""

from typesafe_sdk import Choice, Noul, NoulCriteria, Score

from .questions import TEAMS, URGENCY_LEVELS, WANTS_REFUND_CRITERIA, WANTS_REFUND_INSTRUCTIONS
from .rules import JevAnswers

QUESTIONS = {
    "team": Choice(
        instructions="Which team should handle this customer message?",
        criteria=TEAMS,
    ),
    "wants_refund": Noul(
        instructions=WANTS_REFUND_INSTRUCTIONS,
        criteria=NoulCriteria(**WANTS_REFUND_CRITERIA),
    ),
    "urgency": Score(
        instructions="How urgent is this message?",
        criteria=URGENCY_LEVELS,
    ),
}


def ask_jev(client, message_text: str) -> JevAnswers:
    """Ask all three questions about one message in a single request.

    `client` only needs a `system_one(state, questions)` method, so tests can
    pass a fake client instead of a real TypeSafeClient.
    """
    response = client.system_one(state={"message": message_text}, questions=QUESTIONS)
    team = response.choices["team"]
    refund = response.nouls["wants_refund"]
    urgency = response.scores["urgency"]
    return JevAnswers(
        team=team.choice,
        team_confidence=team.confidence,
        wants_refund=refund.noul,
        urgency_score=urgency.score,
        urgency_confidence=urgency.confidence,
    )
