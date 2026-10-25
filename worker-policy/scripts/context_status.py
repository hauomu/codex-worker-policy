"""Report this Codex thread's current context size against its advisory prompt threshold.

Prints one line, e.g.
  CONTEXT model=gpt-6.1-sol context=312k window=500k prompt_at=400k status=OK

status=PROMPT_USER means: tell the user the size and offer a handover. It never
acts on its own. Thread resolution: --thread, else $CODEX_SESSION_ID, else the
most recently written rollout (flagged as a guess). Reads only the file tail.

Usage: python context_status.py [--thread UUID] [--codex-home PATH]
"""
import argparse, glob, json, os, re

# Advisory prompt points, set below each model's auto-compaction limit so the
# offer arrives while there is still room to hand over deliberately.
PROMPT_AT = {"gpt-6.1-sol": 400_000, "gpt-5.6-sol": 400_000}
DEFAULT_FRACTION = 0.75  # of the reported context window, for unlisted models
TAIL_BYTES = 4 * 1024 * 1024


def find_rollout(codex_home, thread):
    pattern = os.path.join(codex_home, "sessions", "**", f"rollout-*{thread or ''}*.jsonl")
    files = glob.glob(pattern, recursive=True)
    return max(files, key=os.path.getmtime) if files else None


def latest(path):
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - TAIL_BYTES))
        lines = fh.read().decode("utf-8", errors="replace").splitlines()
    model = context = window = None
    for line in reversed(lines):
        if model is None and '"turn_context"' in line:
            try:
                model = json.loads(line)["payload"].get("model")
            except (ValueError, KeyError):
                pass
        elif context is None and '"token_count"' in line:
            try:
                info = json.loads(line)["payload"].get("info") or {}
                context = (info.get("last_token_usage") or {}).get("input_tokens")
                window = info.get("model_context_window")
            except (ValueError, KeyError):
                pass
        if model and context is not None:
            break
    return model, context, window


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default=os.environ.get("CODEX_SESSION_ID"))
    ap.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"))
    args = ap.parse_args()

    path = find_rollout(args.codex_home, args.thread)
    guess = "" if args.thread else " source=newest-rollout(guess)"
    if not path:
        print(f"CONTEXT status=UNKNOWN reason=no-rollout thread={args.thread}")
        return
    model, context, window = latest(path)
    if context is None:
        print(f"CONTEXT model={model} status=UNKNOWN reason=no-token-count{guess}")
        return
    # Hosts, proxies and gateways may report the model with a provider prefix
    # ("provider/model", "provider:model") or different casing; match on the
    # bare name so the per-model threshold applies regardless of how it is routed.
    base_model = re.split(r"[/:]", (model or "").strip().lower())[-1]
    prompt_at = PROMPT_AT.get(base_model) or int((window or 272_000) * DEFAULT_FRACTION)
    status = "PROMPT_USER" if context >= prompt_at else "OK"
    k = lambda n: f"{round(n / 1000)}k" if n else "?"
    print(f"CONTEXT model={model} context={k(context)} window={k(window)} prompt_at={k(prompt_at)} status={status}{guess}")


if __name__ == "__main__":
    main()
