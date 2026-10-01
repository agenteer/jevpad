# A triage tool built by a coding agent

This is what a coding agent (Claude Code) built from `follow-along/` when given the prompt in `1-build-prompt.txt`. Your agent's files, wording and results will differ.

- `1-build-prompt.txt` — the prompt that asks for the tool.
- `2-inspect-prompt.txt` — a follow-up that asks the agent to show what it sends to Jev and to walk one message through the rules.
- `3-change-request.txt` — a request for one change: a message that says the issue is resolved gets its own next step, "no reply needed".
- `project/` — the tool as built, before that change. `triage/questions.py` holds what Jev is asked, and `triage/rules.py` the rules that pick the next step.
- `change.diff` — the change the agent made for the third request. To apply it, from `project/`: `patch -p1 < ../change.diff`.
- `results-before.csv` and `results-after.csv` — the ten sample messages, run live before and after the change.

To run the tool, copy your `.env` into `project/`, then from that folder:

```bash
uv sync
uv run pytest
uv run python -m triage.run
```

The tests need no key. The last command sends the ten messages to Jev with your key.

Two next steps differ between the two results files. M07 moved from `general queue` to `no reply needed`, which is the change. M10 moved from `needs a person` to `billing queue` although no rule for it changed: Jev's confidence in the team was 0.46 in the first run and 0.51 in the second, and the rules send anything below 0.5 to a person. After a change, compare all the rows, because an answer near a threshold can move without any change.
