"""Decide whether a small unit is cheaper for the orchestrator to do itself or to delegate.

Deterministic, linear-in-price cost model (no model call, no network):

  * every orchestrator tool turn re-reads its whole context at the cached input price;
  * material the orchestrator reads itself is paid once at the input price, then again
    (cached) on every later turn while it stays resident;
  * delegation costs the orchestrator a brief, a couple of turns and a resident summary,
    plus the worker's own tokens and the expected cost of the worker failing.

Direct work is selected only for tiny units inside hard caps AND at least
(1 - directMargin) cheaper than the best delegated route, so the model can never be
used to justify absorbing substantive work.

Prints one line, e.g.
  ROUTE=FRONTIER_WORKER reason=DIRECT_MARGIN_NOT_MET direct=$0.0330 frontier=$0.0387 local=- caps=ok model=gpt-6.1-sol

reason is one of DIRECT_CHEAPER, OVER_DIRECT_CAPS, DIRECT_MARGIN_NOT_MET, DELEGATION_CHEAPER.

Usage:
  python route_cost.py --model gpt-6.1-sol --context 120000 --read 3000 --output 500 --turns 2
  python route_cost.py --kind research --json
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "references")

DEFAULT_COST_MODEL = {
    "contextTokens": 40_000,
    "remainingTurns": 10,
    "briefTokens": 400,
    "summaryTokens": 600,
    "delegationTurns": 2,
    "localFailureRate": 0.2,
    "frontierFailureRate": 0.2,
    "frontierBaseTokens": 15_000,
    "directMargin": 0.8,
    "directMaxReadTokens": 6_000,
    "directMaxOutputTokens": 1_500,
    "directMaxTurns": 4,
    "longContextThreshold": 272_000,
    "kindDefaults": {
        "research": {"readTokens": 12_000, "outputTokens": 400, "turns": 5},
        "server_crawl": {"readTokens": 60_000, "outputTokens": 300, "turns": 10},
        "bulk_reduction": {"readTokens": 80_000, "outputTokens": 400, "turns": 8},
        "implementation": {"readTokens": 8_000, "outputTokens": 1_500, "turns": 5},
        "debugging": {"readTokens": 15_000, "outputTokens": 800, "turns": 6},
        "testing": {"readTokens": 6_000, "outputTokens": 300, "turns": 3},
        "review": {"readTokens": 10_000, "outputTokens": 600, "turns": 3},
        "documentation": {"readTokens": 6_000, "outputTokens": 1_500, "turns": 3},
        "other": {"readTokens": 8_000, "outputTokens": 800, "turns": 4},
    },
}


def load_json(name):
    with open(os.path.join(REFS, name), encoding="utf-8") as fh:
        return json.load(fh)


def load_pricing():
    raw = load_json("pricing.json")
    models = {}
    for model_id, price in (raw.get("models") or {}).items():
        def tier(t):
            entry = {k: float(t[k]) for k in ("input", "cachedInput", "output")}
            if any(v < 0 for v in entry.values()):
                raise ValueError(f"invalid prices for {model_id}")
            return entry
        models[model_id.lower()] = {
            **tier(price),
            "long": tier(price["long"]) if price.get("long") else None,
            "longContextThreshold": price.get("longContextThreshold"),
        }
    cost_model = {**DEFAULT_COST_MODEL, **(raw.get("costModel") or {})}
    cost_model["kindDefaults"] = {**DEFAULT_COST_MODEL["kindDefaults"], **((raw.get("costModel") or {}).get("kindDefaults") or {})}
    return {
        "version": raw.get("version", "pricing-unversioned"),
        "models": models,
        "families": {k.lower(): str(v).lower() for k, v in (raw.get("families") or {}).items()},
        "defaultOrchestrator": str(raw.get("defaultOrchestrator", "gpt-6.1-sol")).lower(),
        "frontierWorker": str(raw.get("frontierWorker", "gpt-6-luna")).lower(),
        "costModel": cost_model,
    }


def resolve_price(pricing, model_id):
    """Exact model id first, then the family suffix (gpt-6.1-sol -> "sol"), then the default."""
    mid = str(model_id or pricing["defaultOrchestrator"]).strip().lower()
    if mid in pricing["models"]:
        return mid, pricing["models"][mid], "exact"
    m = re.search(r"-(sol|astra|luna|terra)(?:$|[-.])", mid)
    fam = m and pricing["families"].get(m.group(1))
    if fam and fam in pricing["models"]:
        return fam, pricing["models"][fam], f"family:{m.group(1)}"
    d = pricing["defaultOrchestrator"]
    return d, pricing["models"][d], "default"


def usd(tokens, per_million):
    return tokens * per_million / 1_000_000


def estimate(pricing, *, model, context, remaining_turns, read, output, turns, kind, eligible_local):
    cm = pricing["costModel"]
    k = cm["kindDefaults"].get(kind) or cm["kindDefaults"]["other"]
    context = cm["contextTokens"] if context is None else context
    remaining_turns = cm["remainingTurns"] if remaining_turns is None else remaining_turns
    read = k["readTokens"] if read is None else read
    output = k["outputTokens"] if output is None else output
    turns = max(1, k["turns"] if turns is None else turns)

    orch_id, orch, resolved_by = resolve_price(pricing, model)
    _, f, _ = resolve_price(pricing, pricing["frontierWorker"])
    threshold = orch.get("longContextThreshold") or cm["longContextThreshold"]
    long_ctx = context > threshold
    p = orch["long"] if long_ctx and orch.get("long") else orch

    def resident(tokens):
        return usd(tokens, p["input"]) + usd(tokens * remaining_turns, p["cachedInput"])

    direct = usd(turns * context, p["cachedInput"]) + resident(read) + usd(output, p["output"])
    overhead = (usd(cm["delegationTurns"] * context, p["cachedInput"])
                + usd(cm["briefTokens"], p["output"]) + resident(cm["summaryTokens"]))
    frontier_work = (usd(read + cm["frontierBaseTokens"], f["input"])
                     + usd((read + cm["frontierBaseTokens"]) * turns, f["cachedInput"])
                     + usd(output * 1.5, f["output"]))
    # A failed frontier unit falls back to the orchestrator (break-glass).
    frontier_route = overhead + frontier_work + cm["frontierFailureRate"] * direct
    local_route = overhead + cm["localFailureRate"] * frontier_route
    best = local_route if eligible_local else frontier_route

    within_caps = (read <= cm["directMaxReadTokens"] and output <= cm["directMaxOutputTokens"]
                   and turns <= cm["directMaxTurns"])
    direct_cheaper = within_caps and direct <= best * cm["directMargin"]
    if direct_cheaper:
        route, reason = "ORCHESTRATOR_DIRECT", "DIRECT_CHEAPER"
    else:
        route = "LOCAL_DEFAULT" if eligible_local else "FRONTIER_WORKER"
        if not within_caps:
            reason = "OVER_DIRECT_CAPS"
        elif direct <= best:
            reason = "DIRECT_MARGIN_NOT_MET"  # cheaper, but not by the required margin
        else:
            reason = "DELEGATION_CHEAPER"
    return {
        "route": route, "reasonCode": reason, "pricingVersion": pricing["version"],
        "orchestratorModel": orch_id, "orchestratorPriceResolvedBy": resolved_by,
        "longContext": long_ctx, "withinDirectCaps": within_caps, "eligibleLocal": eligible_local,
        "inputs": {"contextTokens": context, "remainingTurns": remaining_turns,
                   "readTokens": read, "outputTokens": output, "directTurns": turns},
        "usd": {k2: round(v, 6) for k2, v in (("direct", direct), ("local", local_route), ("frontier", frontier_route))},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", help="runtime orchestrator model id (default: pricing.json defaultOrchestrator)")
    ap.add_argument("--context", type=int, help="orchestrator's current context tokens")
    ap.add_argument("--remaining-turns", type=int, help="expected orchestrator turns left in the task")
    ap.add_argument("--read", type=int, help="tokens you would read to do the unit yourself")
    ap.add_argument("--output", type=int, help="tokens you would write")
    ap.add_argument("--turns", type=int, help="tool turns the unit needs")
    ap.add_argument("--kind", default="other", help="defaults for missing estimates: " + ", ".join(DEFAULT_COST_MODEL["kindDefaults"]))
    ap.add_argument("--json", action="store_true", help="print the full estimate as JSON")
    a = ap.parse_args(argv)

    routing = load_json("worker-routing.json")
    eligible_local = bool((routing.get("local") or {}).get("enabled"))
    r = estimate(load_pricing(), model=a.model, context=a.context, remaining_turns=a.remaining_turns,
                 read=a.read, output=a.output, turns=a.turns, kind=a.kind, eligible_local=eligible_local)
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    u = r["usd"]
    print(f"ROUTE={r['route']} reason={r['reasonCode']} direct=${u['direct']:.4f} frontier=${u['frontier']:.4f} "
          f"local={'$%.4f' % u['local'] if eligible_local else '-'} caps={'ok' if r['withinDirectCaps'] else 'exceeded'} "
          f"model={r['orchestratorModel']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
