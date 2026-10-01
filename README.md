# jevpad

A scratchpad for Jev questions: write the questions you want answered about a piece of text, run them, and see what Jev was asked and what it answered.

[Jev](https://docs.typesafe.ai/concepts/system-one) is TypeSafe's decision model. You send it some text and a few questions with fixed answers (which team should handle this, is it asking for a refund, how urgent is it), and it returns typed answers with probabilities instead of prose. jevpad keeps those questions in a file you can edit and prints each call in full, so you can see what a change of wording does to the answers.

jevpad is an open-source project by [Agenteer](https://agenteer.com), built on TypeSafe's Python library. It is not a TypeSafe product.

Tutorial: [Jev AI Full Tutorial: From First Try to Real Applications](https://agenteer.com/resources/jev-ai-full-tutorial/). Video: [Jev AI Explained: What It Is, Why It's Different, How to Use It](https://youtu.be/_eQVS_Cvypo).

## Install

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/agenteer/jevpad.git
cd jevpad
uv sync
```

`uv sync` installs jevpad into a `.venv` folder inside the project, so the commands below start with `uv run`.

## Look around without a key

The two example applications come with hand-written practice answers, so you can see what jevpad prints before you connect it to Jev:

```bash
uv run jevpad messages --mode fixture --input data/messages.csv
uv run jevpad reading --mode fixture
```

Each result is headed `FIXTURE · NOT MODEL OUTPUT`. Two reports from live runs are in `examples/reports/`; open them in a browser.

## Connect it to Jev

Get an API key from the [TypeSafe console](https://console.typesafe.ai/keys), or from [Vercel AI Gateway](https://vercel.com/ai-gateway), which also serves Jev. Then:

```bash
cp .env.example .env
```

Open `.env` and switch on the lines for your route by removing the `#`: one line for TypeSafe, three or four for Vercel. Check the connection:

```bash
uv run jevpad doctor --live
```

It prints your settings (not the key), makes one small call, and names the model that answered. Live calls are billed to your key.

## Ask a question

```bash
uv run jevpad try "I paid for the same order twice. Please return only the duplicate payment."
```

`try` sends your text with the three questions in `recipes/try/questions.yaml` and prints what it sent, each question with its options, and Jev's answers with their probabilities. Edit that file, or pass your own with `--questions`, and run it again to see what changes.

To do the same in a browser page on your own machine:

```bash
uv run jevpad playground
```

## Run your own questions on your own data

Write your questions in a YAML file (start from `examples/questions/support-triage.yaml`) and run them on one text or on every row of a CSV:

```bash
uv run jevpad run --questions examples/questions/support-triage.yaml --text "My invoice shows the wrong company name."
uv run jevpad run --questions examples/questions/support-triage.yaml --input data/messages.csv --export --html out/run.html
```

Each question has a `type` and `instructions`:

- `choice` picks one of the `options` you list, each with a description.
- `noul` answers yes or no, with optional `criteria` for what counts as yes.
- `score` rates the text against the ordered `levels` you describe.

The CSV needs a header row; the text comes from the `text` column, or the one you name with `--column`. `--export` writes the answers to `out/` as CSV and JSON, and `--html` adds a report. Your input file is not changed.

`run` returns Jev's judgments and stops there. What to do with them is your code's decision.

## Two example applications

Both follow the same pattern: a questions file that Jev answers, and a short rules file in plain Python that turns the answers into a next step.

**Support triage.** For each customer message, Jev picks a team, says whether the message asks for money back, whether it expects a reply, and how urgent it is. The rules turn that into a next step such as a team's review queue, "no reply needed", or a person.

```bash
uv run jevpad messages --input data/messages.csv --export --html out/messages.html
```

Questions: `recipes/messages/questions.yaml`. Rules: `recipes/messages/policy.py`.

**A reading list for each reader.** Jev scores 15 Agenteer Academy articles for each reader in `data/readers.csv`, using each reader's own description and each article's title and description. Every reader gets the whole list in their own order.

```bash
uv run jevpad reading --export --html out/reading.html
uv run jevpad reading --reader dental_office
```

Questions: `recipes/reading/preferences.yaml`. Rules: `recipes/reading/policy.py`. To add yourself, add a row to `data/readers.csv`.

## Compare Jev with another model

`comparison/` runs Jev and GPT-5.4-mini on the same 154 labeled bank customer messages and reports accuracy, speed and cost. See [`comparison/README.md`](comparison/README.md).

## Build your own tool with a coding agent

`follow-along/` is a starting folder for asking a coding agent (Claude Code, Codex or any other) to build a triage tool on Jev. `examples/agent-built-triage/` holds one such build: the prompts, the project the agent wrote, and its results.

## What jevpad records

Every call is saved under `runs/`, and every table says where its answers came from:

- `LIVE` is a fresh call to Jev.
- `FIXTURE` is a hand-written practice answer.
- `REPLAY` shows a saved live call again.

`uv run jevpad runs` lists the saved calls, and `uv run jevpad replay RUN_ID` shows one again. A call that is refused because the service is busy is retried up to five times; a call that still fails is reported as failed, not as an answer. To see that path without a real failure, add `--inject-fault ratelimit` to a command.

## What is in the folder

- `jevpad/` — the tool: the commands, the Jev client, the saved records and the exports.
- `recipes/` — the questions and rules for `try` and for the two example applications.
- `data/` — the sample messages, readers and articles.
- `examples/` — a questions file to copy, two sample reports, and a triage tool built by a coding agent.
- `follow-along/` — the starting folder for building your own tool with a coding agent.
- `comparison/` — the Jev and GPT-5.4-mini comparison.
- `hello_jev.py` — the short example from TypeSafe's Python SDK page, to run the library without jevpad: `uv run --env-file .env python hello_jev.py`.
- `tests/` — tests that run without a key: `uv run pytest -q`.

## License

MIT; see [`LICENSE`](LICENSE). Third-party data and files are listed in [`NOTICE`](NOTICE).
