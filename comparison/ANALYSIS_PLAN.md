# September two-model statistics plan

Written on 24 September 2026 before the September test-split calls, after the development runs, and hashed into FROZEN.json. The four-model comparison reuses its accuracy denominators, Wilson intervals and exact McNemar tests for all six model pairs.

The run procedure below describes the September two-model comparison: two passes and a direct OpenAI route for GPT-5.4-mini. The saved 25 October four-model comparison instead uses one pass through Vercel AI Gateway for all four models; see FOUR_MODEL_PLAN.md and config-gateway-four.json for its settings.

## Runs
- The test split (154 examples: 2 per label from BANKING77 test.csv, seed 20260924) runs **exactly twice, back to back**, with the frozen `config.json`. **Pass 1 is the headline** regardless of how it compares with pass 2. Pass 2 reports run-to-run agreement per model (same settings) and a second timing sample.
- A network baseline (`netbase.sh`: 20 × connect / TLS / time-to-first-byte to each host) runs before pass 1, between passes, and after pass 2.
- Calls are sequential (concurrency 1), alternate which model goes first per example, and use the identical retry policy in `config.json`. Concurrent gateway traffic is not controlled; observed availability and timing are saved with the results.

## Accuracy
- Denominator = all 154 examples. An example with no valid answer after the retry budget counts as wrong and is also listed as unanswered.
- Reported beside it: correct / answered.
- Paired 2×2 (both right, only Jev, only LLM, both wrong) on the full denominator and on the both-answered pairs; exact two-sided McNemar on discordant pairs.
- Wording rule: no "better/worse at accuracy" wording unless one model leads on the paired discordant count with exact McNemar p < 0.05; otherwise "no clear difference on this sample". Wilson 95% intervals are shown for each accuracy.

## Time
- Two rows per model: served-request time (final attempt) and time to a usable result (all attempts and waits). Median, p95 (nearest rank; the 8th slowest of 154) and worst. p95 is labelled rough at this n.
- Jev's gateway-reported time at TypeSafe (`provider_ms`) is shown as a separate line; the headline stays client-observed for both models. The LLM is called directly at api.openai.com; Jev through Vercel AI Gateway — named in the table.

## Availability
- A separate block: attempts refused (429), timeouts, examples affected, never-answered ids, the gateway message quoted once, retry-after presence, and the LLM's retry count under the same policy.

## Cost
- The comparison row is catalog cost for both: usage × list price with source and date (Jev \$0.042 per million input tokens, output free; gpt-5.4-mini \$0.75 in / \$4.50 out per million). "Actually charged" is shown separately (Jev \$0 under Vercel's promotion ending 2026-09-25). No cost ratio is computed from a \$0 charge. Token counts are not shown side by side (the two providers count differently).

## Claims we will not make at this n
Per-label accuracy, leaderboard comparisons, p99, calibration, a general winner, or any cost/speed ratio beyond this task and setup. The confidence-gated view of Jev is a feature sidebar with kept-count denominators, not part of the comparison table.
