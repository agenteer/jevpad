# TypeSafe's own example (the Sync tab of its quickstart), unchanged, from https://docs.typesafe.ai/sdk/python
# Run from this folder: uv run --env-file .env python hello_jev.py
# The library reads TYPESAFE_API_KEY, TYPESAFE_BASE_URL and TYPESAFE_DEFAULT_MODEL from your .env.
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

with TypeSafeClient() as client:
    response = client.system_one(
        state={"document": "I was charged twice. Please fix this ASAP."},
        questions={
            "billing": Noul(instructions="Is this ticket about billing?"),
            "tone": Choice(
                instructions="What is the customer's tone?",
                criteria={"calm": None, "frustrated": None, "angry": None},
            ),
            "urgency": Score(
                instructions="How urgent is this ticket?",
                criteria=["can wait", "this week", "today"],
            ),
        },
    )

print(response.nouls["billing"].noul)
print(response.choices["tone"].choice)
print(response.scores["urgency"].score)
