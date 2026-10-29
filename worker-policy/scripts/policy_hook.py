"""Codex hook for worker-policy: a prompt reminder, a context check and a spawn check.

Register this one script for three events in ~/.codex/hooks.json (see README):

  UserPromptSubmit  injects a ~100-token routing reminder, plus the handover offer
                    once the context passes the model's prompt point.
  PostToolUse       silent until the context passes the prompt point, then the
                    handover offer once per 50k of further growth.
  PreToolUse        (matcher "spawn_agent") denies a worker spawn that lacks an
                    explicit model, reasoning_effort or fork_turns "none", uses
                    Astra, or names a model/effort that is not a role in
                    references/worker-routing.json. Silent when the spawn is fine.

Applies only when the runtime model is in the Sol or Astra family; a Luna runtime
gets only the spawn check (Luna never spawns paid workers). Other models are
left alone. Never blocks anything else, and any internal error exits 0 silently,
so a broken hook can never stop a session.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context_status  # noqa: E402

STEP = 50_000
STATE_DIR = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"),
                         "hooks", "state", "worker_policy")
REMINDER = (
    "worker-policy applies (you are the orchestrator). Work that brings new material into your context "
    "(bulk reads, research, implementation, tests) goes to workers on the ladder for its unit kind (SKILL.md §3). "
    "Before doing any unit yourself, state its routing receipt. Spawn every worker with explicit model, "
    "reasoning_effort and fork_turns \"none\". When a ladder runs out, re-plan once or report; never absorb the unit."
)


def base(model):
    return re.split(r"[/:]", (model or "").strip().lower())[-1]


def family(model):
    m = re.search(r"-(sol|astra|luna)(?:$|[-.])", base(model))
    return m.group(1) if m else None


def allowed_roles():
    with open(os.path.join(HERE, "..", "references", "worker-routing.json"), encoding="utf-8") as fh:
        roles = json.load(fh).get("roles") or {}
    return {(base(v["model"]), v.get("effort")) for v in roles.values() if isinstance(v, dict) and v.get("model")}


def context_note(data):
    """Handover offer once the context passes the prompt point, then every STEP more; else None."""
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return None
    model, context, window = context_status.latest(path)
    if context is None:
        return None
    prompt_at = context_status.PROMPT_AT.get(base(model or data.get("model"))) \
        or int((window or 272_000) * context_status.DEFAULT_FRACTION)
    bucket = -1 if context < prompt_at else (context - prompt_at) // STEP
    state = os.path.join(STATE_DIR, re.sub(r"[^\w.-]", "_", data.get("session_id") or "unknown") + ".json")
    try:
        with open(state, encoding="utf-8") as fh:
            warned = json.load(fh).get("bucket", -1)
    except (OSError, ValueError):
        warned = -1
    if bucket != warned:  # grew past a step, or shrank after compaction: record it
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(state, "w", encoding="utf-8") as fh:
            json.dump({"bucket": bucket, "context": context}, fh)
    if bucket <= warned:
        return None
    k = round(context / 1000)
    return (f"Context is about {k}k tokens, past the {prompt_at // 1000}k handover point (worker-policy §9). "
            "Tell the user the size once and offer a handover: finish the current unit, write the project's "
            "continuity notes, and let a fresh thread resume. Then continue as the user chooses; do not hand over, "
            "compact or stop on your own.")


def spawn_problem(tool_input):
    """Why a spawn_agent call breaks the policy, or None."""
    model, effort = tool_input.get("model"), tool_input.get("reasoning_effort")
    missing = [name for name, value in (("model", model), ("reasoning_effort", effort)) if not value]
    if missing:
        return f"spawn_agent is missing {' and '.join(missing)}, so the worker would inherit yours."
    if tool_input.get("fork_turns") != "none":
        return 'spawn_agent must pass fork_turns "none" and carry everything the unit needs in the brief.'
    if family(model) == "astra":
        return "Never spawn an Astra worker."
    if (base(model), effort) not in allowed_roles():
        roles = ", ".join(f"{m}@{e}" for m, e in sorted(allowed_roles()))
        return f"{base(model)}@{effort} is not a worker role in worker-routing.json; use one of: {roles}."
    return None


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    event = data.get("hook_event_name")
    fam = family(data.get("model"))
    if fam not in ("sol", "astra", "luna"):
        return
    if event == "PreToolUse" and data.get("tool_name") in ("spawn_agent", "Agent"):
        tool_input = data.get("tool_input") or {}
        reason = ("A Luna orchestrator never spawns workers (worker-policy §1); continue directly."
                  if fam == "luna" else spawn_problem(tool_input))
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": "worker-policy: " + reason}}))
        return
    if fam == "luna" or event not in ("UserPromptSubmit", "PostToolUse"):
        return
    notes = [REMINDER] if event == "UserPromptSubmit" else []
    note = context_note(data)
    if note:
        notes.append(note)
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(notes)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
