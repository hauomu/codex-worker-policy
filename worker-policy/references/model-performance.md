# Model performance by reasoning effort

Checked 2026-10-20. Scores and costs per task are **vendor-reported** by OpenAI: the GPT-6 Sol/Luna launch charts and the GPT-6.1 Sol release, as summarised by [AI Catchup](https://aicatchup.com/news/openai-gpt-6-sol-luna) and [Emergent](https://emergent.sh/learn/gpt-6-1-sol-benchmarks). Independent runs differ a little; for example, [Artificial Analysis](https://artificialanalysis.ai/models/gpt-6-luna) measured Luna at max at 64% rather than 66.6% on DeepSWE in the Codex harness. `model-performance.json` beside this file is the machine-readable copy that `scripts/route_cost.py` loads; keep the two in sync.

## Why token price is the wrong comparison

Luna's token price is 1/20 of 6.1 Sol's, but at higher effort it thinks for longer, and at lower effort it fails more. What a unit actually costs is the cost per task divided by the chance of solving it, plus what each failure costs the orchestrator (noticing it, reviewing the result, re-briefing):

    cost per solve = (cost per task + (1 - score) × failure penalty) / score

`python scripts/route_cost.py --rank` prints this for every model and effort, with the penalty from `pricing.json` (`costModel.failurePenaltyUsd`, default $0.10).

## DeepSWE 1.1 (repository bug fixing; the primary benchmark)

| Model | Effort | Solved | $/task | $/solve (penalty $0.10) |
| --- | --- | ---: | ---: | ---: |
| gpt-6-luna | low | 2.4% | 0.006 | 4.32 |
| gpt-6-luna | medium | 44.5% | 0.052 | 0.24 |
| **gpt-6-luna** | **high** | **59.3%** | **0.084** | **0.21** |
| gpt-6-luna | xhigh | 61.3% | 0.11 | 0.24 |
| gpt-6-luna | max | 66.6% | 0.22 | 0.38 |
| **gpt-6.1-sol** | **low** | **64.4%** | **0.17** | **0.32** |
| gpt-6.1-sol | medium | 73.0% | 0.42 | 0.61 |
| gpt-6.1-sol | high | 75.2% | 0.65 | 0.90 |
| gpt-6.1-sol | xhigh | 71.9% | 0.79 | 1.14 |
| gpt-6.1-sol | max | 71.9% | 1.57 | 2.22 |
| gpt-6-sol | low | 37.2% | 0.16 | 0.60 |
| gpt-6-sol | medium | 56.6% | 0.38 | 0.75 |
| gpt-6-astra | xhigh | 74.1% | 4.43 | 6.01 |

(Full grids for gpt-6-sol and gpt-6-astra are in the JSON.)

## Other benchmarks (Luna; Sol is GPT-6 Sol)

| Benchmark | Luna medium | Luna high | Luna xhigh | Luna max | Sol low |
| --- | ---: | ---: | ---: | ---: | ---: |
| FrontierCode 1.1 (coding) | 35.5% / $0.053 | 37.3% / $0.067 | 37.1% / $0.073 | 42.4% / $0.11 | 37.3% / $0.45 |
| AutomationBench 1.0.6 (tool automation) | 9.4% / $0.016 | 14.5% / $0.021 | 12.6% / $0.025 | 20.7% / $0.037 | 21.2% / $0.19 |
| OSWorld 2.0 offline (computer use) | 31.5% / $0.062 | 41.4% / $0.12 | 46.7% / $0.16 | 52.7% / $0.27 | 43.9% / $0.97 |
| Factual error rate (lower is better) | 17.5% | 12.5% | 10.2% | 7.6% | 11.4% |

## Independent: Artificial Analysis, Luna vs 6.1 Sol by effort

From the Artificial Analysis comparisons of [Luna `high` vs 6.1 Sol `low`](https://artificialanalysis.ai/models/comparisons?compare=gpt-6-luna-high%2Cgpt-6-1-sol-low) and of [Luna `high`/`xhigh`/`max` vs 6.1 Sol `low`/`medium`](https://artificialanalysis.ai/models/comparisons?compare=gpt-6-luna-high%2Cgpt-6-luna%2Cgpt-6-luna-xhigh%2Cgpt-6-1-sol-medium%2Cgpt-6-1-sol-low) (Intelligence Index v4.3.2), checked 2026-10-20. Artificial Analysis reports one cost per task averaged over the whole index, so per-solve figures use that average for every benchmark. The JSON stores these as the `aa-*` benchmarks; `route_cost.py --rank --benchmark <name>` ranks by any of them.

| Benchmark | Luna `high` | Luna `xhigh` | Luna `max` | Sol `low` | Sol `medium` |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Terminal-Bench 4.0 (agentic coding & terminal use)** | **5%** | **8%** | **13%** | **31%** | **48%** |
| AutomationBench-AA (agentic SaaS workflows) | 48% | 48% | 53% | 53% | 63% |
| SciCode (coding) | 50% | 52% | 55% | 53% | 53% |
| Humanity's Last Exam (reasoning & knowledge) | 33% | 34% | 39% | 47% | 50% |
| **GDP.pdf (document reasoning)** | **18%** | **19%** | **23%** | **27%** | **30%** |
| CritPt (physics reasoning) | 15% | 17% | 19% | 25% | 28% |
| **AA-LCR v1.1 (long-context reasoning)** | **79%** | **80%** | **83%** | **84%** | **83%** |
| **AA-Omniscience index (knowledge minus hallucination, −100…100)** | **−6** | **−2** | **1** | **38** | **40** |
| Intelligence Index | 33 | 35 | 38 | 42 | 48 |
| Cost per task | $0.03 | $0.04 | $0.07 | $0.13 | $0.21 |
| Output tokens per task | 20k | 27k | 50k | 4k | 8k |
| Time per task | 167 s | 222 s | 408 s | 92 s | 184 s |

Expected cost per solve ($0.10 failure penalty):

| Benchmark | Luna `high` | Luna `xhigh` | Luna `max` | Sol `low` | Sol `medium` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Terminal-Bench 4.0 | 2.50 | 1.65 | 1.21 | 0.64 | **0.55** |
| GDP.pdf | **0.62** | 0.64 | 0.64 | 0.75 | 0.93 |
| AA-LCR v1.1 | **0.07** | 0.08 | 0.11 | 0.17 | 0.27 |

Luna `high` wins on AA-Briefcase (1186 vs 1117 for Sol `low`) and GDPval-AA (1340 vs 1315), both agentic knowledge-work Elo ratings; Luna `max` and Sol `medium` lead both. Luna's Omniscience score stays near zero at every effort: from memory it answers wrongly about as often as rightly, so research briefs make it work from sources, not recall. For extraction, `xhigh` adds about one point on both document benchmarks for a third more cost and time; `max` adds 4–5 points and cuts OpenAI's measured factual error rate from 12.5% to 7.6%.

## What the policy takes from this

- **Research is split by how much judgement it needs,** because a wrong research answer passes silently instead of failing a test, so the $0.10 failure penalty understates its cost. *Extraction* (locate and collect from given sources) stays on Luna `high`: on long-context reasoning it is within 5 points of Sol `low` at about a third of the cost per solve, and every claim must be cited. *Interpretation* (summarise and interpret documents) starts on Luna `max`, the one effort step that clearly improves document reasoning and factual accuracy; `xhigh` is skipped. *Analysis* (compare, decide, diagnose, explain) starts on 6.1 Sol `low`, because Luna's judgement and recall are weak at every effort.
- **Terminal-heavy units start on 6.1 Sol `low`.** Debugging, running and fixing tests, builds and environment setup are what Terminal-Bench measures. There Sol is about four times cheaper per solve, and it finishes faster. Their retry is 6.1 Sol `medium`; Luna is skipped.
- **Luna `high` is the default worker for everything else.** It is the cheapest per solved coding task. `medium` (the Codex default a worker inherits when no effort is passed) solves a quarter fewer tasks, and `low` is unusable for agent work.
- **`xhigh` is not worth it as a default.** It adds about 2 points on DeepSWE for 31% more cost, and scores *below* `high` on FrontierCode and AutomationBench.
- **`max` is the retry.** It is the strongest Luna setting on every benchmark, so it is the best second attempt at a unit `high` failed, even though it is too expensive per solve to be the default.
- **6.1 Sol `low` is the last worker rung,** never GPT-6 Sol: at `low`, 6.1 Sol solves 64.4% of DeepSWE tasks and GPT-6 Sol 37.2%, at nearly the same price. On coding, 6.1 Sol `low` is actually cheaper per solve than Luna `max`. It is a different model, so it is also less likely to repeat Luna's mistake.
- **Benchmark tasks are harder than a typical delegated unit,** so `route_cost.py` scales failure rates by `costModel.unitHardness` (default 0.5: Luna `high` fails about 20% of units).
