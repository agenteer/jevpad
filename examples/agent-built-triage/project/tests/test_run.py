from triage.run import DEFAULT_INPUT, FIELDNAMES, load_messages, triage_all


def test_loads_all_ten_messages():
    rows = load_messages(DEFAULT_INPUT)
    assert len(rows) == 10
    assert {row["id"] for row in rows} == {f"M{i:02d}" for i in range(1, 11)}
    assert all(row["text"].strip() for row in rows)


class FakeClient:
    def system_one(self, state, questions):
        from types import SimpleNamespace

        return SimpleNamespace(
            choices={"team": SimpleNamespace(choice="general", confidence=0.9)},
            nouls={"wants_refund": SimpleNamespace(noul=0.1)},
            scores={"urgency": SimpleNamespace(score=0.5, confidence=0.9)},
        )


def test_triage_all_produces_one_row_per_message_with_expected_columns():
    messages = [{"id": "M01", "text": "Hello"}, {"id": "M02", "text": "World"}]
    rows = triage_all(messages, FakeClient())

    assert len(rows) == 2
    assert set(rows[0]) == set(FIELDNAMES)
    assert rows[0]["next_step"] == "general queue"
