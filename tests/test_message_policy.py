from recipes.messages.policy import proposed_action


def test_message_policy_keeps_action_in_code():
    answers = {
        "team": {"choice": "billing", "confidence": 0.9},
        "requests_refund": {"noul": 0.95},
        "expects_reply": {"noul": 0.9},
        "urgency": {"score": 0.5},
    }
    assert proposed_action(answers) == "billing review queue — no refund issued"

