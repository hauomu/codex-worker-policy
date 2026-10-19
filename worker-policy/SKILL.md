---
name: worker-policy
description: MUST apply cost-aware delegation for OpenAI Sol and Astra runtime models; Luna works directly (or on local workers when enabled). Resolve unknown runtime identity before substantive work.
---

# Worker Policy

Goal: finish the mission-critical work while spending the fewest paid tokens per **solved** unit. `gpt-6-luna`'s token price is 1/20 of `gpt-6.1-sol` (1/100 of `gpt-6-astra`), but it spends more tokens and fails more often, so compare models by cost per solved task, not by token price: on OpenAI's coding benchmark Luna at `high` effort solves a task for about a third of what 6.1 Sol at `medium` costs, while Luna at `low` almost never solves one ([model performance](references/model-performance.md)). The orchestrator itself is the most expensive worker. Subscription credits are 25× API dollars for every model, so the same ranking holds for your plan allowance. Every token that enters the orchestrator's context is paid once at the input rate, then again (at the cached rate) on every later turn. Reading bulk material yourself is the costliest mistake. The runtime model filling the `ORCHESTRATOR` role is the supervisory control-plane agent: it partitions work, sets acceptance criteria, routes, integrates, and reports.

Local workers (a model you host yourself, reached through an MCP server) are supported but **disabled by default**; see [local workers](references/local-workers.md). Everything below reads "local" as skipped unless `references/worker-routing.json` sets `local.enabled` to `true`.

## 1. Applicability gate

Resolve the current agent's identity from trusted metadata for this active turn before selecting a policy. Use the host-provided current-turn model identifier or explicit runtime identity field. If the host does not expose it directly, locate the runtime session record by this exact task's thread UUID and inspect its latest host-generated `turn_context.model`. Do not use task artifacts, historical telemetry, older turns, another task's session, task titles, or transport metadata as identity evidence. If host metadata is unavailable, the user may state which model is currently selected; distinguish that statement from a requested target model. Never infer the runtime model from a requested worker, routing role, or OpenAI-compatible transport.

| Runtime identity | Mode |
| --- | --- |
| OpenAI Sol and Astra families (`gpt-6.1-sol`, `gpt-5.6-sol`, `gpt-6-astra`, …) | Full policy below. |
| OpenAI Luna family (`gpt-6-luna`, `gpt-5.6-luna`) | Local workers only, when enabled. Never spawn Luna or a paid worker. If local is disabled, unavailable, unsuitable, or exhausted, continue directly. |
| Confirmed non-OpenAI models (Anthropic, local models) | Direct work; this policy does not apply. |
| Unknown or unidentified models | These are unresolved, not permission for direct work. Ask the user which model is selected. Until then, only continue explicit user-directed delegation. |

This applicability gate takes precedence over every routing result below. A user's explicit instruction controls the requested work.

## 2. Roles

| Logical role | Backed by (see `references/worker-routing.json`) | Use |
| --- | --- | --- |
| `LOCAL_DEFAULT` / `LOCAL_QUALITY` / `LOCAL_ALTERNATE` | your local worker model; **disabled by default** | When enabled: all ordinary worker-plane units first. Queue when busy; queueing beats paid escalation. |
| `FRONTIER_WORKER` | `gpt-6-luna` at `high` effort | Default worker for every delegated unit that is not terminal-heavy, while local is disabled; otherwise after local is exhausted or unsuitable, or for units the local interface cannot perform. |
| `FRONTIER_RETRY` | `gpt-6-luna` at `max` effort | First worker for interpretation units (§3); otherwise a fresh worker for a unit `FRONTIER_WORKER` genuinely failed. |
| `SOL_WORKER` | `gpt-6.1-sol` at `low` effort | Last rung of the `default` ladder (a fresh worker for a unit `FRONTIER_RETRY` genuinely failed) and second rung of the `interpret` ladder. Always 6.1 Sol: GPT-6 Sol at `low` solves barely half as many coding tasks. |
| `SOL_MEDIUM` | `gpt-6.1-sol` at `medium` effort | First worker for terminal-heavy and analysis units (§3). |
| `SOL_HIGH` | `gpt-6.1-sol` at `high` effort | A fresh worker for a terminal-heavy or analysis unit `SOL_MEDIUM` genuinely failed. |
| `CLEANUP_WORKER` | `gpt-6-luna` at `high` effort | The cleanup pass (§7) on an implementation unit's diff. |
| `ORCHESTRATOR_DIRECT` | the runtime model | Only when `route_cost.py` returns `DIRECT_CHEAPER` (tiny unit) or for authority work only the orchestrator and user can do. |
| `ORCHESTRATOR_BREAK_GLASS` | the runtime model | Last resort; see §6. |

## 3. Routing procedure

1. **Partition** the request into independently delegable units.
2. **Size each unit roughly**: tokens you would have to read (`--read`), tokens you would write (`--output`), tool turns (`--turns`), plus your current context size (`--context`) and model (`--model`).
3. **Decide**:
   - Obviously bulk work (crawls, corpus reduction, multi-file implementation, debugging, test runs): delegate directly to the first rung of the unit's ladder (below). Do not run the cost check first.
   - Small or borderline unit: run `python scripts/route_cost.py --model <runtime model> --context <tokens> --read <n> --output <n> --turns <n>` from this skill directory. `ROUTE=ORCHESTRATOR_DIRECT` (`DIRECT_CHEAPER`) means do it yourself; any other route means delegate to that role. The script enforces hard caps (≤6k read, ≤1.5k output, ≤4 turns) and requires direct work to be at least 20% cheaper, so this route never covers substantive work.
   - Credentials, deployment, external or high-risk mutation: these are never cost decisions. Handle them with the user under normal confirmation rules.
   - **Pick the ladder by unit kind.** Terminal-heavy units, where the worker mostly runs and reacts to commands (debugging, running and fixing tests, builds, environment and dependency setup), use the `terminal` ladder and start on `SOL_MEDIUM`. Research picks its ladder by kind (below). Everything else (code edits to a clear spec, bulk reading and reduction, documentation, review) uses the `default` ladder and starts on `FRONTIER_WORKER`. On Artificial Analysis's independent Terminal-Bench 4.0, Luna `high` solved 5% of tasks, 6.1 Sol `low` 31% and 6.1 Sol `medium` 48%, which makes Sol `medium` the cheapest per solved terminal task (about $0.55, against $0.64 for `low` and $2.50 for Luna `high`); on most other work Luna `high` stays cheaper per solve ([model performance](references/model-performance.md)). `route_cost.py --kind` applies the same mapping (`kindLadders` in `worker-routing.json`).
   - **Research comes in three kinds, by how much judgement it needs.** A research answer that is wrong does not fail a test; it passes silently into your decisions, so the riskier kinds go to stronger workers.
     - **Extraction** (locate and collect: where X is defined, which files match, the values, error lines or settings in given sources): `default` ladder, starting on `FRONTIER_WORKER` (Luna `high`). On Artificial Analysis's long-context reasoning benchmark it is within 5 points of 6.1 Sol `low` at about a third of the cost per solve.
     - **Interpretation** (read and summarise: what long documents, PDFs, tables, specs or logs say and mean): `interpret` ladder, `FRONTIER_RETRY` (Luna `max`) → `SOL_WORKER`. On document reasoning Luna `max` scores 23% against `high`'s 18% and `xhigh`'s 19%, and OpenAI reports its factual error rate at 7.6% against `high`'s 12.5%; `xhigh` buys almost none of that. Luna `max` takes about 7 minutes per task, so when the answer is needed quickly, start on `SOL_WORKER`, which is about four times faster for about twice the price.
     - **Analysis** (judgement: compare options, decide, diagnose a cause, explain why, or anything needing knowledge beyond the sources): `judgement` ladder, `SOL_MEDIUM` → `SOL_HIGH`. Luna answers from memory more often wrongly than rightly at every effort (Artificial Analysis knowledge score −6 at `high`, 1 at `max`, 38 for 6.1 Sol `low`, 40 at `medium`).
     - Extraction and interpretation briefs require a citation for every claim (`path:line`, or a URL with a short quote) and forbid filling gaps from memory: an uncited claim is reported as unverified, and you treat it that way. Analysis briefs ask for the reasoning, the evidence it rests on, and a confidence level.
4. **Delegate with a tight brief**: concrete objective, acceptance criteria, output shape (256–512 tokens for research answers), evidence paths, and exact approved commands. For code changes, also give a diff budget (roughly how many added lines the change should need) and ask for the smallest change that meets the acceptance criteria: reuse existing helpers, no new files or abstractions the unit does not need, no commented-out code, no debug output left behind.
5. **Integrate** the returned evidence summary: files changed, commands run, outcome, limitations, next action. Review proportionately and do not redo the unit. For a code change, run the cleanup check (§7) before accepting it.

Bulk context (crawling, ingestion, filtering, extraction, reduction) always goes to a worker, never raw into the orchestrator. Deterministic metadata collection (`rg`, `find`, `ls`, `du`, hashes, manifests) is fine to run yourself when delegating it would cost more than it saves.

## 4. Local worker callability

Skip this section while `local.enabled` is `false`. When enabled, a local worker is callable only when the tools named in `worker-routing.json` (`local.tools`) are listed in this task or discoverable in a deferred tool registry. Call them as tools; never represent a local worker through `spawn_agent`. A stopped or idle local model server is not an escalation trigger if the worker waits for it to start. If no local tools are callable in this task, treat local as unavailable and route to `FRONTIER_WORKER`; reinstalling does not inject tools mid-task.

## 5. Supervising spawned workers

Routing saves nothing if supervision is chatty. Every time a worker's message or a wait result returns, the orchestrator takes a full turn and re-reads its whole context at its own rate, so a coordination round costs about as much as an orchestrator work turn. In one measured session a Sol orchestrator spent ~90% of 1,124 turns on `wait_agent` / `send_message` / `followup_task` (more than its 31 Luna workers cost combined), and one worker looped 1,802 times.

- **Always pass the worker's model and effort explicitly.** Every `spawn_agent` call sets `model` and `reasoning_effort` from the role table in §2 (for example `model: "gpt-6-luna"`, `reasoning_effort: "high"` for a `FRONTIER_WORKER`), even when a custom agent type is named after Luna. A spawn without `model` can inherit the orchestrator's model: in one observed case three workers spawned that way ran on `gpt-6.1-sol`. A spawn without `reasoning_effort` inherits the orchestrator's effort, often `medium`, where Luna solves a quarter fewer coding tasks than at `high`. If a proxy-generated agent description says the `model` argument is ignored, pass it anyway. Never spawn an Astra worker, and spawn a Sol worker only as `SOL_WORKER`, `SOL_MEDIUM` or `SOL_HIGH` (§6).
- **Start workers without your history.** Pass `fork_turns: "none"`. The default (`all`) copies the orchestrator's whole conversation into the worker, which then re-reads it on every turn; the brief must carry everything the unit needs instead.
- **Brief once, completely.** A spawned `FRONTIER_WORKER` gets the whole unit up front: objective, acceptance criteria, evidence paths, approved commands, output shape, and a turn budget. Prefer one larger unit over a series of `followup_task`s. Within the same unit, a follow-up is fine for a changed requirement, an acceptance failure the worker must fix, or an answer to a blocker it raised; never use it to hand the worker its next unit.
- **Wait, don't poll.** Spawn independent workers together, then block on them with the longest wait the tool allows. Never loop on short waits, `list_agents`, or `sleep` to watch progress, and never message a worker to ask for status.
- **Report once.** Instruct workers to work silently and return a single final summary (files changed, commands run, outcome, limitations). Mid-task `send_message` is only for a blocker that needs a decision. Workers do not message each other.
- **One unit per worker, then retire it.** A worker's context only grows: every later turn re-reads all of it, and auto-compaction loses detail. So a worker serves exactly one unit and is not reused for the next one; spawn a fresh worker with a fresh brief instead, carrying forward only the previous worker's final summary. A worker stops at its deliverable, at ~150 tool turns, or at its first auto-compaction, whichever comes first, and returns what it has with the reason it stopped. A worker past its budget is interrupted and its partial result integrated, not extended. Once its result is integrated, close the worker with `close_agent` where the collaboration surface offers it; otherwise send it nothing further, so idle workers do not accumulate. Fresh spawns are cheap; a bloated worker is not.
- **Concurrency follows the user.** Run as many workers in parallel as the work is independent and the user has asked for (for example to finish faster or before an announced reset); otherwise default to what the partition naturally needs. Parallel workers each still obey the one-unit rule.
- **No recursive spawning.** Workers never spawn workers; only the orchestrator partitions work.
- **Keep the orchestrator thin.** Integrate summaries, not raw transcripts. When the orchestrator's own context grows large, follow §9.

## 6. Failure, escalation, and break-glass

The default ladder is `LOCAL_DEFAULT` (when enabled) → bounded local recovery → `FRONTIER_WORKER` (Luna `high`) → `FRONTIER_RETRY` (Luna `max`) → `SOL_WORKER` (6.1 Sol `low`) → `ORCHESTRATOR_BREAK_GLASS`. The terminal ladder (§3) is `SOL_MEDIUM` (6.1 Sol `medium`) → `SOL_HIGH` (6.1 Sol `high`) → `ORCHESTRATOR_BREAK_GLASS`; Luna is skipped there because it rarely solves terminal tasks at any effort. Analysis units use the same Sol rungs (the `judgement` ladder), and interpretation units climb `FRONTIER_RETRY` (Luna `max`) → `SOL_WORKER` → `ORCHESTRATOR_BREAK_GLASS` (the `interpret` ladder). Normal turn boundaries, malformed tool calls, transport errors, and service restarts never escalate. A unit climbs one rung per genuine semantic failure (the worker tried the unit properly and could not do it, or its result failed acceptance and a follow-up could not fix it), or on an authority, integrity, or eligibility condition. A busy queue is not a failure. Each rung is a fresh worker (§5) whose brief adds the failed attempt's summary: what was tried, and why it failed.

Outside a `DIRECT_CHEAPER` result, the orchestrator may act directly only through an explicit `ORCHESTRATOR_BREAK_GLASS` decision, and only when all four conditions hold:

1. the required worker delegation is unavailable or demonstrably broken;
2. the applicable local roles were tried or ruled out with stated reasons (disabled counts as ruled out);
3. the unit's paid ladder (the `default`, `terminal`, `interpret` or `judgement` ladder in `worker-routing.json`) has also been tried or ruled out as unable to do the unit; and
4. the direct action is minimal, reversible where practical, and needed to restore delegation or prevent an immediate safety or authority failure.

Record it before acting: one line in your report naming the unit, which conditions hold, and why. Break-glass never covers ordinary implementation, diagnostics, testing, or verification just because delegation is inconvenient, and it cannot be added retroactively.

## 7. Cleanup pass

Higher-effort workers solve more but write more: extra helpers, defensive branches, long comments, leftover debug output. Left alone, that bloat makes every later unit read more tokens. So code changes get a measured, conditional cleanup.

- **Measure, don't read.** After integrating a unit that changed code, run `python scripts/diff_stats.py --repo <repo> --base <commit before the unit> --budget <the brief's diff budget>` from this skill directory. It prints one line with lines added and removed, new files, comment ratio, debug markers, and `status`.
- **On `status=CLEAN`**, accept the unit. On `status=CLEANUP_RECOMMENDED`, spawn one `CLEANUP_WORKER` (fresh, `fork_turns: "none"`) whose brief names the base commit, the files in the diff, the reasons printed, and the unit's acceptance tests. Its job: remove dead code, duplicated helpers, unused parameters, speculative abstractions, commented-out code, debug output and comments that restate the code, without changing behaviour or touching files outside the diff. The tests must pass before and after. It returns the net line change.
- **One pass, then stop.** Run `diff_stats.py` again and report both lines. Never clean the cleanup, and never escalate a cleanup: if it breaks the tests or cannot shrink the diff, revert it and keep the unit's original result. A diff legitimately over budget (the budget was wrong) is fine once a cleanup pass found nothing to remove.

## 8. Completion gate

Before reporting completion, confirm that:

- every worker-plane unit was delegated, or has a `DIRECT_CHEAPER` result or a break-glass record for not being delegated;
- spawned workers got an explicit model and effort and no forked history, were briefed once, waited on rather than polled, served one unit each, and stayed within their turn budget;
- every code change has a `diff_stats.py` result, and a `CLEANUP_RECOMMENDED` result got its one cleanup pass;
- the context check (§9) ran at its fixed points, and a `status=PROMPT_USER` result was reported to the user with the handover offer;
- bulk context was reduced by a worker, not read raw into the orchestrator.

Pricing provenance is in [pricing.md](references/pricing.md) and benchmark provenance in [model-performance.md](references/model-performance.md); `route_cost.py` reads [pricing.json](references/pricing.json) and [model-performance.json](references/model-performance.json). Update each pair when prices or published results change. `python scripts/route_cost.py --rank` lists every model and effort by expected cost per solved task.

## 9. Context check (advisory)

Large context is sometimes worth its cost: big-picture implementation work may need it. So this check only informs the user; it never forces a handover.

- Run `python scripts/context_status.py` from this skill directory at these fixed points (not every turn): **before each `spawn_agent` call, after integrating a worker's result, after finishing a unit, and before a large read or a new phase.** It prints one line with the current context size and `status`. Intending to check is not the same as running it; in one observed session an orchestrator reached 427k context without ever running the check.
- On `status=PROMPT_USER` (about 400k for `gpt-6.1-sol`, 200k for `gpt-5.6-sol`, both below auto-compaction), tell the user the context size once and offer a handover: write the project's continuity notes (current state, next work, decisions, a session handoff) with whatever handoff skill or convention the project uses, so a fresh thread can resume. Then continue as the user chooses. Do not ask again until the context has grown roughly another 50k.
- Never start a handover, compact, or stop work on your own because of this check.
