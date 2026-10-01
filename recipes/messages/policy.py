from __future__ import annotations


# Illustrative teaching thresholds; these values have not been evaluated for production use.
LOW_TEAM_CONFIDENCE = 0.55
REFUND_REQUEST = 0.70
NO_REPLY = 0.30
HIGH_URGENCY = 1.50


def proposed_action(answers: dict) -> str:
    team = answers["team"]
    if team["confidence"] < LOW_TEAM_CONFIDENCE:
        return "human review: low routing confidence"
    if answers["expects_reply"]["noul"] < NO_REPLY:
        return "no reply needed"
    prefix = team["choice"].replace("_", " ")
    if team["choice"] == "billing" and answers["requests_refund"]["noul"] >= REFUND_REQUEST:
        return "billing review queue — no refund issued"
    if answers["urgency"]["score"] >= HIGH_URGENCY:
        return f"priority {prefix} review"
    return f"{prefix} review queue"

