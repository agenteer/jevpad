# follow-along

A starting folder for building your own support-triage tool on Jev with a coding agent. It is almost empty on purpose: the agent writes the tool.

What is here:

- `data/messages.csv` — ten sample customer messages.
- `.env.example` — the settings for connecting to Jev. Copy it to `.env` and fill in one route, or copy the `.env` you already made in the main folder.
- `.claude/skills/typesafe-ai/` — TypeSafe's agent skill (from [typesafe-ai/skills](https://github.com/typesafe-ai/skills)), which tells a coding agent how to build with Jev.

Start your coding agent in this folder (Claude Code, Codex or any other):

```bash
cp ../.env .env
claude
```

Then send it the prompt in `../examples/agent-built-triage/1-build-prompt.txt`. The agent reads TypeSafe's documentation, builds the tool, and runs it on the ten messages with your key; those calls are billed to your key.

`../examples/agent-built-triage/` has the tool one agent built from this folder, to compare with yours afterwards.
