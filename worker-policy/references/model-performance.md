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

## What the policy takes from this

- **Luna `high` is the default worker.** It is the cheapest per solved coding task. `medium` (the Codex default a worker inherits when no effort is passed) solves a quarter fewer tasks, and `low` is unusable for agent work.
- **`xhigh` is not worth it as a default.** It adds about 2 points on DeepSWE for 31% more cost, and scores *below* `high` on FrontierCode and AutomationBench.
- **`max` is the retry.** It is the strongest Luna setting on every benchmark, so it is the best second attempt at a unit `high` failed, even though it is too expensive per solve to be the default.
- **6.1 Sol `low` is the last worker rung,** never GPT-6 Sol: at `low`, 6.1 Sol solves 64.4% of DeepSWE tasks and GPT-6 Sol 37.2%, at nearly the same price. On coding, 6.1 Sol `low` is actually cheaper per solve than Luna `max`. It is a different model, so it is also less likely to repeat Luna's mistake.
- **Benchmark tasks are harder than a typical delegated unit,** so `route_cost.py` scales failure rates by `costModel.unitHardness` (default 0.5: Luna `high` fails about 20% of units).
