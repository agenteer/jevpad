test split: 154 examples. Unanswered/refused examples count wrong.

| Model | Correct / all | Correct / answered | Wilson 95% | Served median / p95 / worst (ms) | Usable median / p95 / worst (ms) | Gateway USD |
|---|---|---|---|---|---|---|
| jev | 114/154 | 114/154 | 66.6%–80.3% | 156 / 306 / 1986 | 156 / 306 / 1986 | 0.00666 |
| llm | 110/154 | 110/154 | 63.8%–78.0% | 744 / 1115 / 6627 | 744 / 1115 / 6628 | 0.06722 |
| decisions | 107/154 | 107/153 | 61.8%–76.2% | 255 / 561 / 2816 | 255 / 561 / 2816 | 0.01014 |
| luna | 115/154 | 115/154 | 67.3%–80.9% | 1169 / 1868 / 2247 | 1169 / 1868 / 2248 | 0.008724 |

p95 is rough at this n. Pairwise exact two-sided McNemar tests (unadjusted):
- jev/llm, all: n=154, both right=100, only first=14, only second=10, both wrong=30, p=0.541256; no clear difference on this sample.
- jev/llm, both_answered: n=154, both right=100, only first=14, only second=10, both wrong=30, p=0.541256; no clear difference on this sample.
- jev/decisions, all: n=154, both right=101, only first=13, only second=6, both wrong=34, p=0.167068; no clear difference on this sample.
- jev/decisions, both_answered: n=153, both right=101, only first=12, only second=6, both wrong=34, p=0.237885; no clear difference on this sample.
- jev/luna, all: n=154, both right=108, only first=6, only second=7, both wrong=33, p=1; no clear difference on this sample.
- jev/luna, both_answered: n=154, both right=108, only first=6, only second=7, both wrong=33, p=1; no clear difference on this sample.
- llm/decisions, all: n=154, both right=99, only first=11, only second=8, both wrong=36, p=0.647606; no clear difference on this sample.
- llm/decisions, both_answered: n=153, both right=99, only first=10, only second=8, both wrong=36, p=0.814529; no clear difference on this sample.
- llm/luna, all: n=154, both right=102, only first=8, only second=13, both wrong=31, p=0.38331; no clear difference on this sample.
- llm/luna, both_answered: n=154, both right=102, only first=8, only second=13, both wrong=31, p=0.38331; no clear difference on this sample.
- decisions/luna, all: n=154, both right=100, only first=7, only second=15, both wrong=32, p=0.133801; no clear difference on this sample.
- decisions/luna, both_answered: n=153, both right=100, only first=7, only second=14, both wrong=32, p=0.189247; no clear difference on this sample.

Availability and catalog cost (separate from gateway charge):
- jev: {"attempts_total": 154, "attempts_refused_429": 0, "timeouts_or_connection": 0, "retries": 0, "retry_after_sent": false, "refusal_message": null}; unanswered=[]; refusals=[]; catalog USD=0.00666.
- llm: {"attempts_total": 154, "attempts_refused_429": 0, "timeouts_or_connection": 0, "retries": 0, "retry_after_sent": false, "refusal_message": null}; unanswered=[]; refusals=[]; catalog USD=0.06722.
- decisions: {"attempts_total": 154, "attempts_refused_429": 0, "timeouts_or_connection": 0, "retries": 0, "retry_after_sent": false, "refusal_message": null}; unanswered=['test-050']; refusals=['test-050']; catalog USD=0.01014.
- luna: {"attempts_total": 154, "attempts_refused_429": 0, "timeouts_or_connection": 0, "retries": 0, "retry_after_sent": false, "refusal_message": null}; unanswered=[]; refusals=[]; catalog USD=0.008724.
