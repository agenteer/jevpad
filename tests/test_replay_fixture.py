from jevpad.modes import fixture_answers


def test_fixture_answers_are_named_non_model_data():
    answers = fixture_answers("messages", "M01")
    assert answers["team"]["choice"] == "billing"

