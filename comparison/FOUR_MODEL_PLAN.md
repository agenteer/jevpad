# Four-model comparison — October 25, 2026

Jev, GPT-5.4-mini, Decisions API (GPT-6 Luna) and GPT-6 Luna chat classify the same 154 BANKING77 messages into 77 labels. All use Vercel AI Gateway with pinned providers, one request at a time, the same instruction and the same six-attempt retry rule. Settings are fixed before the run.

GPT-6 Luna chat matches GPT-5.4-mini's prompt, strict enum schema, 512-token cap, temperature 0 and reasoning none. Decisions API gets a typed Choice question and API-default reasoning. Jev chooses its highest-probability label. The version behind `typesafe-ai/jev` cannot be confirmed.

Order repeats every eight messages:

1. Jev, GPT-5.4-mini, Decisions API, GPT-6 Luna chat
2. GPT-5.4-mini, Decisions API, GPT-6 Luna chat, Jev
3. Decisions API, GPT-6 Luna chat, Jev, GPT-5.4-mini
4. GPT-6 Luna chat, Jev, GPT-5.4-mini, Decisions API
5. GPT-6 Luna chat, Decisions API, GPT-5.4-mini, Jev
6. Jev, GPT-6 Luna chat, Decisions API, GPT-5.4-mini
7. GPT-5.4-mini, Jev, GPT-6 Luna chat, Decisions API
8. Decisions API, GPT-5.4-mini, GPT-6 Luna chat, Jev

Each model appears twice in each position; each pair precedes the other four times. The 154 messages contain 19 complete cycles and a two-message tail. Ordering does not depend on results.

ANALYSIS_PLAN.md's denominator, Wilson 95% ranges and independent exact two-sided McNemar tests apply to all six pairs. Refusals and unanswered messages count wrong. Tests are unadjusted; no general winner is inferred. Timing includes retries and waits. Displayed milliseconds are rounded; full precision remains in the data.

From the repository root:

```sh
./comparison/run_comparison_v2.sh
```

To check settings without sending requests:

```sh
comparison/.venv/bin/python comparison/run_comparison_v2.py --check
```

The comparison checks frozen source and configuration hashes and requires the freeze to be committed before sending requests. It reads the gateway key, runs one comparison, saves JSONL, summary, Markdown and HTML, and prints relative result locations. Progress shows this run's gateway charge. A stopped run saves its answers; another full run is never started automatically.

The cumulative budget includes earlier four-model requests, with a $0.05 reserve before each request and a $1 ceiling. Unknown charges stop the run. All attempt charges remain in the data. Avoid concurrent invocations against this budget meter.

The September two-model comparison remains available as `run_comparison.py`.
