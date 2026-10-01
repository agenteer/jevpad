# Comparing Jev with GPT-5.4-mini

This folder runs Jev and GPT-5.4-mini on the same 154 labeled bank customer messages and reports how many each got right, how long each took and what each cost.

## The task

The messages come from BANKING77, a public dataset of customer messages to a bank, each labeled with one of 77 intents. The sample is two messages per intent, 154 in all, and is fixed in `manifest.json`.

Both models get the same message, the same one-sentence instruction and the same 77 labels. Jev gets them as one Choice question. GPT-5.4-mini gets them as structured output limited to the 77 labels, with reasoning effort `none` and temperature 0, and a one-line system message. Both are called through Vercel AI Gateway. The settings are in `config-gateway-temp0.json`.

## Run it

You need a Vercel AI Gateway key with credits: either `AI_GATEWAY_API_KEY` in your shell, or the `.env` in the main folder set up for the Vercel route. A run sends 308 requests and takes about three to seven minutes; ours cost about \$0.07.

```bash
cd comparison
uv sync
uv run python run_comparison.py
uv run python score_comparison.py
```

`run_comparison.py` saves each answer in `results/`, with the charge Vercel reports for it. `score_comparison.py` calls no model: it counts how many each model got right, how long they took and what they cost, prints a table, and writes a report page next to the run, `results/<run>.report.html`, that explains the numbers.

Before it sends anything, the runner checks that the settings, the sample and the runner files are unchanged, and stops if they are not; the recorded hashes are in the `FROZEN*.json` files. That keeps your run comparable with the saved one.

## The saved run

`results/` has one saved run and its report page. To print its table without a key:

```bash
uv run python score_comparison.py results/test-20260930T224309Z-gateway-temp0-pass5.jsonl
```

In that run Jev got 116 of the 154 right and GPT-5.4-mini 111, which is not a clear difference at this sample size. Jev's median answer took 231 ms against 911 ms, at about a tenth of the cost. It is a small test on one task. To choose a model for your own work, run the comparison on your own labeled messages.

## Use it on your own messages

`sample.py` is the script that picked the 154 messages. Adapt it to a labeled file of your own, choose the sample and the settings first, and run the test afterwards.

## Data

BANKING77 is by PolyAI, under CC BY 4.0; see `data/NOTICE`.
