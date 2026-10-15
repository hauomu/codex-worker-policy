# Local workers (disabled by default)

A local worker is a model you host yourself (llama.cpp, vLLM, LM Studio, Ollama, …) that the orchestrator calls through an MCP server. It has zero marginal paid cost, so when it is available the policy routes ordinary worker-plane units to it **before** `gpt-6-luna`. Most users do not run one, so this route ships switched off. Nothing in this file applies until you enable it.

## Enabling

1. Install an MCP server that exposes your local model as bounded worker tools (research/reduction, and ideally a workspace task tool that edits files and runs approved commands).
2. Register the server in Codex (`~/.codex/config.toml`, `[mcp_servers.<name>]`).
3. Edit `worker-routing.json`:

   ```json
   "local": { "enabled": true, "server": "<name>", "tools": ["<exact tool names>"] },
   "roles": { "LOCAL_DEFAULT": "<model id>", "LOCAL_QUALITY": "<model id>", "LOCAL_ALTERNATE": "<model id>", "FRONTIER_WORKER": "gpt-6-luna" }
   ```

4. Run `python tests/policy_lint.py`. It checks that an enabled local route names its server, tools, and a model for every local role.

`scripts/route_cost.py` reads `local.enabled` and then compares direct work against the local route instead of the frontier route.

## What the policy expects from a local worker

- **Callable as tools, not agents.** The orchestrator calls the tools directly; a local worker is never represented through `spawn_agent`.
- **Bounded turns.** Each call does one bounded model turn (a wall-clock deadline and a tool-operation cap, e.g. 240 s and 10 operations) and returns a status such as `COMPLETE`, `CONTINUE`, `SEMANTIC_FAILURE`, `BLOCKED`, or `UNRECOVERABLE`. A `CONTINUE` is a normal boundary, not a failure.
- **Owns its retry state.** The worker (or its controller) counts attempts, not the orchestrator.
- **Waits for its own model server.** An idle or stopped model server that starts on demand is not an escalation trigger.
- **Returns evidence, not transcripts.** Files changed, commands run, outcome, limitations, next action.

## Attempt accounting (for controller authors)

Use these terms consistently:

- **JOB** — the complete delegated bounded work unit.
- **SEMANTIC_ATTEMPT** — one genuine attempt to solve the unit. Two failed semantic attempts escalate to `FRONTIER_WORKER`.
- **MODEL_TURN** — one bounded inference/tool-loop segment inside a semantic attempt.
- **RECOVERY** — a repair, restart, or continuation caused by a recoverable harness or infrastructure problem.

One semantic attempt may contain many model turns and recoveries; starting another turn or recovery never increments the semantic attempt. Classify outcomes with typed classes (`PROTOCOL_ERROR`, `TRANSPORT_ERROR`, `SERVICE_ERROR`, `TURN_LIMIT`, `CONTEXT_LIMIT`, `TOOL_ERROR`, `SEMANTIC_FAILURE`, `AUTHORITY_FAILURE`, `WORKSPACE_INTEGRITY_FAILURE`). Malformed tool calls, temporary HTTP failures, service restarts, and normal turn boundaries use their own bounded recovery budgets and never consume a semantic attempt. Authority and workspace-integrity failures follow their own route and are never disguised as semantic failures.

At each turn boundary, checkpoint controller-observable state (job id, objective, attempt and turn numbers, workspace identity and diff stats, latest result, next action) so a continuation resumes the same workspace instead of restarting from a clean tree. Reject any late result from a turn that was already cancelled.

Freeze the routing policy into each job when it is created: a running job keeps the rules and prices it started with; only new jobs pick up edits to this skill.
