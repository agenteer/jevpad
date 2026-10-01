from types import SimpleNamespace

from triage.jev_client import ask_jev


class FakeResponse:
    def __init__(self, team, team_confidence, refund, urgency, urgency_confidence):
        self.choices = {"team": SimpleNamespace(choice=team, confidence=team_confidence)}
        self.nouls = {"wants_refund": SimpleNamespace(noul=refund)}
        self.scores = {"urgency": SimpleNamespace(score=urgency, confidence=urgency_confidence)}


class FakeClient:
    def __init__(self, response):
        self._response = response
        self.last_call = None

    def system_one(self, state, questions):
        self.last_call = {"state": state, "questions": questions}
        return self._response


def test_ask_jev_maps_response_fields_onto_jev_answers():
    response = FakeResponse(team="billing", team_confidence=0.92, refund=0.7, urgency=2.3, urgency_confidence=0.6)
    client = FakeClient(response)

    answers = ask_jev(client, "I want my money back.")

    assert answers.team == "billing"
    assert answers.team_confidence == 0.92
    assert answers.wants_refund == 0.7
    assert answers.urgency_score == 2.3
    assert answers.urgency_confidence == 0.6


def test_ask_jev_sends_the_message_as_state():
    client = FakeClient(FakeResponse("sales", 0.8, 0.1, 0.5, 0.8))

    ask_jev(client, "Hello there")

    assert client.last_call["state"] == {"message": "Hello there"}
    assert set(client.last_call["questions"]) == {"team", "wants_refund", "urgency"}
