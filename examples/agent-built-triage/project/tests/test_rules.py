from triage.rules import JevAnswers, next_step


def _answers(**overrides):
    base = dict(
        team="general",
        team_confidence=0.9,
        wants_refund=0.1,
        urgency_score=0.5,
        urgency_confidence=0.9,
    )
    base.update(overrides)
    return JevAnswers(**base)


def test_low_team_confidence_needs_a_person():
    assert next_step(_answers(team_confidence=0.4)) == "needs a person"


def test_team_confidence_at_floor_is_trusted():
    assert next_step(_answers(team="general", team_confidence=0.5)) == "general queue"


def test_high_urgency_is_urgent():
    assert next_step(_answers(urgency_score=2.0)) == "urgent"


def test_low_confidence_wins_over_urgency():
    # If we don't trust the routing, that matters even for an urgent message.
    answers = _answers(team_confidence=0.3, urgency_score=3.0)
    assert next_step(answers) == "needs a person"


def test_urgency_wins_over_refund():
    answers = _answers(urgency_score=2.5, wants_refund=0.9)
    assert next_step(answers) == "urgent"


def test_refund_request_goes_to_billing_queue_even_if_team_is_not_billing():
    answers = _answers(team="technical_support", wants_refund=0.9)
    assert next_step(answers) == "billing queue"


def test_non_billing_default_goes_to_team_queue():
    answers = _answers(team="sales", wants_refund=0.1)
    assert next_step(answers) == "sales queue"
