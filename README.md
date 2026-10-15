# codex-worker-policy

A [Codex](https://developers.openai.com/codex) skill that makes expensive models act as **orchestrators** and hand the actual work to cheap workers, so a session spends a fraction of the paid tokens it otherwise would.

`gpt-6-luna` costs about 1/20 of `gpt-6.1-sol` and 1/100 of `gpt-6-astra`. Every token an orchestrator reads is paid again (at the cached rate) on every later turn, so the cheapest thing a Sol or Astra session can do is plan, brief, and integrate summaries, while Luna workers do the reading and writing. This skill tells Codex how to do that without wasting the savings on chatty supervision.

## What it does

- **Identity gate.** Applies the full policy only when the running model is Sol or Astra. Luna works directly (it never spawns paid workers); other providers' models are untouched; an unknown model is asked about rather than assumed.
- **Cost-based routing.** `scripts/route_cost.py` decides whether a small unit is cheaper to do directly or to delegate, from published prices. Direct work is allowed only for tiny units (≤6k tokens read, ≤1.5k written, ≤4 turns) that are also at least 20% cheaper. Bulk work always goes to a worker.
- **Supervision rules that keep the savings.** Brief once, wait instead of polling, one unit per worker, always pass `model: "gpt-6-luna"` explicitly, no recursive spawning. In one measured session, chatty supervision cost more than all 31 workers combined.
- **Escalation ladder and break-glass.** Workers escalate only after two genuine failures; the orchestrator may take over only under four stated conditions, recorded before acting.
- **Advisory context check.** `scripts/context_status.py` reports the session's context size and suggests a handover before auto-compaction. It never stops work by itself.
- **Optional local workers.** If you host your own model behind an MCP server, it can take ordinary units before Luna at zero marginal cost. This route ships **disabled**; see [local workers](worker-policy/references/local-workers.md).

## Install

Requires Codex with skills support and Python 3.10+.

1. Copy the `worker-policy` folder into your Codex skills directory:

   ```bash
   git clone https://github.com/hauomu/codex-worker-policy.git
   cp -r codex-worker-policy/worker-policy ~/.codex/skills/worker-policy
   ```

   On Windows: `Copy-Item -Recurse codex-worker-policy\worker-policy $env:USERPROFILE\.codex\skills\worker-policy`

2. Optionally add a line to `~/.codex/AGENTS.md` so every session applies it:

   ```text
   Use the `worker-policy` skill for cost-aware delegation. Never spawn another Sol.
   ```

3. Check the install:

   ```bash
   python ~/.codex/skills/worker-policy/tests/policy_lint.py
   ```

## Using the scripts

```bash
# Should this 2k-token lookup be done directly or delegated?
python scripts/route_cost.py --model gpt-6.1-sol --context 120000 --read 2000 --output 300 --turns 2
# ROUTE=FRONTIER_WORKER reason=DIRECT_MARGIN_NOT_MET direct=$0.0330 frontier=$0.0387 local=- caps=ok model=gpt-6.1-sol

# How big is this session's context?
python scripts/context_status.py
# CONTEXT model=gpt-6.1-sol context=196k window=475k prompt_at=400k status=OK
```

`--kind research|implementation|debugging|testing|review|documentation|server_crawl|bulk_reduction` fills in typical sizes when you have no estimate. `--json` prints the full calculation.

## Configuration

- **Prices:** `references/pricing.json` (machine-readable) and `references/pricing.md` (sources). Prices were checked on 2026-10-13; update both when OpenAI changes them. Cost-model tunables are documented in `pricing.md`.
- **Worker roles:** `references/worker-routing.json`. `FRONTIER_WORKER` is `gpt-6-luna`; the local roles stay `null` until you enable local workers.
- **Model names** reflect OpenAI's lineup as of October 2026. Unknown model ids are priced as the default orchestrator.

## License

[Apache License 2.0](LICENSE) with the [Commons Clause](https://commonsclause.com/) condition. In short: use it, change it and share it for free, including at work, with credit. You may not sell it, or sell a product or service whose value comes substantially from it, such as bundling it into a paid agent harness or platform as a feature. Because of that condition, this is source-available rather than OSI-approved open source. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for the binding terms.

Not affiliated with or endorsed by OpenAI.
