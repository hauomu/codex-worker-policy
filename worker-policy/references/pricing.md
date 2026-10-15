# Worker pricing

Checked 2026-10-13 against the official [API pricing page](https://developers.openai.com/api/docs/pricing) and the [Codex/Work pricing page](https://learn.chatgpt.com/docs/pricing). `pricing.json` beside this file is the machine-readable copy that `scripts/route_cost.py` loads; keep the two in sync.

## API prices (USD per 1M tokens, standard tier)

Short context is ≤272K input tokens per request; long is above that.

| Model | Short input | Short cached | Short output | Long input | Long cached | Long output |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-6-astra | $10.00 | $1.00 | $50.00 | $20.00 | $2.00 | $75.00 |
| gpt-6.1-sol | $2.00 | $0.10 | $10.00 | $4.00 | $0.20 | $15.00 |
| gpt-6-sol | $2.00 | $0.20 | $10.00 | $4.00 | $0.40 | $15.00 |
| gpt-6-luna | $0.10 | $0.01 | $0.50 | $0.20 | $0.02 | $0.75 |
| gpt-5.6-sol | $4.00 | $0.40 | $20.00 | $8.00 | $0.80 | $30.00 |
| gpt-5.6-terra | $2.00 | $0.20 | $12.00 | $4.00 | $0.40 | $18.00 |
| gpt-5.6-luna | $0.20 | $0.02 | $1.20 | $0.40 | $0.04 | $1.80 |

Batch is 50% of standard. Cache writes ($2.50 for 6.1 Sol short) are API-only. GPT-5.6 Sol promotional pricing runs at least through 2026-11-21.

## Subscription (ChatGPT sign-in) usage

Codex signed in with ChatGPT draws on the plan allowance, then on credits. **Credit rates are exactly 25× the API USD rates for every model** (e.g. 6.1 Sol = 50 / 2.5 / 250 credits per 1M input / cached / output), with no cache-write charge. So the USD cost model ranks routes identically for API-key and subscription use.

Published local-message estimates per 5-hour window (Plus and Standard Business; Pro has no 5-hour limit, weekly limits may apply):

| Model | Messages / 5h |
| --- | ---: |
| GPT-6 Astra | 5–45 |
| GPT-6.1 Sol | 15–160 |
| GPT-6 Sol | 15–150 |
| GPT-6 Luna | 350–3,000 |

Fast mode burns included usage at 2.5× (credits 2×); Ultrafast at 8× (credits 6×). OpenAI's own guidance for stretching limits matches this policy: smaller prompts, fewer source files, tighter outputs, smaller AGENTS.md, fewer MCP servers. Exact per-plan allowances are not published; check `/status` or the usage dashboard.

## Ratios that drive routing

- **Luna vs 6.1 Sol:** 20× cheaper input and output, 10× cheaper cached input.
- **Astra vs 6.1 Sol:** 5× input/output, 10× cached. An Astra orchestrator makes every delegation decision stronger in favour of workers.
- **6.1 Sol cached input is 5% of its input price** (most models are 10%), so re-reading a long context is relatively cheap on 6.1 Sol; reading *new* material is what costs.
- A local worker, when enabled, has zero marginal paid cost; latency, bounded interfaces, and retry risk still matter, so the cost model includes a local failure rate.

## Cost-model tunables (`pricing.json` → `costModel`)

| Key | Default | Meaning |
| --- | ---: | --- |
| `contextTokens` | 40,000 | Orchestrator context assumed when `--context` is not given. |
| `remainingTurns` | 10 | Later turns that re-read anything the orchestrator reads now. |
| `briefTokens` / `summaryTokens` | 400 / 600 | Cost of writing a brief and keeping a worker's summary resident. |
| `delegationTurns` | 2 | Orchestrator turns spent spawning and integrating. |
| `frontierBaseTokens` | 15,000 | Baseline context a fresh worker starts with. |
| `localFailureRate` / `frontierFailureRate` | 0.2 / 0.2 | Probability a delegated unit fails and falls back up the ladder. |
| `directMargin` | 0.8 | Direct work must be at least 20% cheaper than delegating. |
| `directMaxReadTokens` / `directMaxOutputTokens` / `directMaxTurns` | 6,000 / 1,500 / 4 | Hard caps: above any of these, direct work is never selected. |
| `longContextThreshold` | 272,000 | Long-context pricing applies above this (per-model override allowed). |
