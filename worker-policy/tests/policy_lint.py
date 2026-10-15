"""Deterministic lint for the worker-policy invariants.

Checks structure and configuration rather than exact sentences, so the policy
can be edited for brevity without breaking the lint, while the safety and cost
gates stay present and the config files stay consistent.

Run: python tests/policy_lint.py
"""

from pathlib import Path
import json
import re
import sys
import unittest


POLICY_ROOT = Path(__file__).parents[1]
LOCAL_ROLES = ("LOCAL_DEFAULT", "LOCAL_QUALITY", "LOCAL_ALTERNATE")
sys.path.insert(0, str(POLICY_ROOT / "scripts"))
import route_cost  # noqa: E402

# (description, regex) pairs that must each match the policy text.
REQUIRED_PATTERNS = (
    ("applicability gate section", r"^## \d+\. Applicability gate"),
    ("identity from trusted active-turn metadata", r"trusted metadata for this active turn"),
    ("turn_context.model fallback", r"`turn_context\.model`"),
    ("user-stated vs requested model distinction", r"distinguish that statement from a requested target model"),
    ("Sol/Astra full policy", r"Sol and Astra families.*Full policy"),
    ("Luna never spawns paid workers", r"Luna family.*Never spawn Luna or a paid worker"),
    ("non-OpenAI direct", r"non-OpenAI models.*Direct work"),
    ("unknown identity unresolved", r"unresolved, not permission for direct work"),
    ("gate precedence", r"applicability gate takes precedence"),
    ("local route disabled by default", r"disabled by default"),
    ("all logical roles", r"`LOCAL_DEFAULT`.*`LOCAL_QUALITY`.*`LOCAL_ALTERNATE`"),
    ("frontier role", r"`FRONTIER_WORKER`"),
    ("direct role", r"`ORCHESTRATOR_DIRECT`"),
    ("cost decision code", r"`DIRECT_CHEAPER`"),
    ("cost script referenced", r"scripts/route_cost\.py"),
    ("direct hard caps stated", r"hard caps"),
    ("authority never a cost decision", r"never cost decisions"),
    ("bulk to workers", r"Bulk context.*always goes to a worker"),
    ("no spawn_agent for local", r"never represent a local worker through `spawn_agent`"),
    ("explicit worker model", r"Always pass the worker's model explicitly"),
    ("escalation ladder", r"`LOCAL_DEFAULT`.*→ .*`FRONTIER_WORKER` → `ORCHESTRATOR_BREAK_GLASS`"),
    ("two semantic failures", r"two genuine semantic failures"),
    ("non-escalating failures", r"Normal turn boundaries, malformed tool calls, transport errors, and service restarts never escalate"),
    ("break-glass condition: frontier tried", r"`FRONTIER_WORKER` has also been tried or ruled out"),
    ("no retroactive break-glass", r"cannot be added retroactively"),
    ("completion gate section", r"^## \d+\. Completion gate"),
    ("context check section", r"^## \d+\. Context check"),
)

REQUIRED_REFERENCES = ("local-workers.md", "pricing.md", "pricing.json", "worker-routing.json")
# Install-specific material that must never ship in a published copy of the skill.
FORBIDDEN = [
    (r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+\b", "CGNAT/Tailscale address"),
    (r"\b(10|192\.168)\.\d+\.\d+(\.\d+)?\b", "private LAN address"),
    (r"/home/[a-z]", "home-directory path"),
    (r"[A-Za-z]:\\Users\\", "Windows user path"),
]
# Optional, never committed: one term per line (host names, user names, ...).
_private_terms = POLICY_ROOT / "tests" / "private-terms.txt"
if _private_terms.is_file():
    for term in _private_terms.read_text(encoding="utf-8").split():
        FORBIDDEN.append((rf"(?i)\b{re.escape(term)}\b", f"private term '{term}'"))


def lint() -> list[str]:
    problems: list[str] = []
    policy = (POLICY_ROOT / "SKILL.md").read_text(encoding="utf-8")
    for label, pattern in REQUIRED_PATTERNS:
        if not re.search(pattern, policy, re.MULTILINE | re.DOTALL):
            problems.append(f"policy missing: {label}")
    if len(re.findall(r"^[1-4]\. ", policy.split("only when all four conditions hold", 1)[-1], re.MULTILINE)) < 4:
        problems.append("policy missing: four numbered break-glass conditions")
    for name in REQUIRED_REFERENCES:
        if not (POLICY_ROOT / "references" / name).is_file():
            problems.append(f"missing reference file: references/{name}")
    for path in sorted(POLICY_ROOT.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".json", ".yaml", ".py") and path.name != Path(__file__).name \
                and "__pycache__" not in path.parts:
            text = path.read_text(encoding="utf-8")
            for pattern, what in FORBIDDEN:
                if re.search(pattern, text):
                    problems.append(f"{path.relative_to(POLICY_ROOT)}: contains {what}")
    try:
        routing = json.loads((POLICY_ROOT / "references" / "worker-routing.json").read_text(encoding="utf-8"))
        local = routing.get("local") or {}
        if not isinstance(local.get("enabled"), bool):
            problems.append("worker-routing.json: local.enabled must be true or false")
        elif local["enabled"]:
            if not local.get("server") or not local.get("tools"):
                problems.append("worker-routing.json: an enabled local route needs a server and its tool names")
            if any(not routing["roles"].get(role) for role in LOCAL_ROLES):
                problems.append("worker-routing.json: an enabled local route needs a model for every local role")
        if not routing["roles"].get("FRONTIER_WORKER"):
            problems.append("worker-routing.json: FRONTIER_WORKER must name a model")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        problems.append(f"worker-routing.json invalid: {error}")
    try:
        pricing = json.loads((POLICY_ROOT / "references" / "pricing.json").read_text(encoding="utf-8"))
        models = pricing["models"]
        for model_id, price in models.items():
            if not all(isinstance(price.get(k), (int, float)) and price[k] >= 0 for k in ("input", "cachedInput", "output")):
                problems.append(f"pricing.json: invalid prices for {model_id}")
        for key in ("defaultOrchestrator", "frontierWorker"):
            if pricing.get(key) not in models:
                problems.append(f"pricing.json: {key} is not a listed model")
        for family, model_id in pricing.get("families", {}).items():
            if model_id not in models:
                problems.append(f"pricing.json: family {family} maps to unlisted {model_id}")
        frontier, sol = models.get(pricing.get("frontierWorker")), models.get(pricing.get("defaultOrchestrator"))
        if frontier and sol and not frontier["output"] < sol["output"]:
            problems.append("pricing.json: frontier worker must be cheaper than the orchestrator")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        problems.append(f"pricing.json invalid: {error}")
    return problems


def classify_runtime_identity(model_id: str | None) -> str:
    """Classify only a positively identified active runtime model ID."""
    if not isinstance(model_id, str) or not model_id.strip():
        return "unresolved"
    identity = model_id.strip().lower()
    if re.fullmatch(r"gpt-[a-z0-9.]+-(?:sol|astra)", identity):
        return "full_policy"
    if re.fullmatch(r"gpt-[a-z0-9.]+-luna", identity):
        return "luna"
    if identity.startswith(("anthropic/", "claude-", "local/")):
        return "direct"
    return "unresolved"


class RuntimeIdentityCases(unittest.TestCase):
    def test_confirmed_modes(self):
        cases = {
            "gpt-5.6-sol": "full_policy",
            "gpt-6.1-sol": "full_policy",
            "gpt-6-astra": "full_policy",
            "gpt-5.6-luna": "luna",
            "gpt-6-luna": "luna",
            "anthropic/claude-fable-5": "direct",
            "local/my-model": "direct",
        }
        for model_id, expected in cases.items():
            with self.subTest(model_id=model_id):
                self.assertEqual(classify_runtime_identity(model_id), expected)

    def test_unknown_identity_never_selects_direct_mode(self):
        for model_id in (None, "", "gpt-5", "OpenAI-compatible", "unknown-model"):
            with self.subTest(model_id=model_id):
                self.assertEqual(classify_runtime_identity(model_id), "unresolved")


class RouteCostCases(unittest.TestCase):
    def setUp(self):
        self.pricing = route_cost.load_pricing()

    def route(self, **kw):
        args = dict(model="gpt-6.1-sol", context=40_000, remaining_turns=None, read=500, output=200,
                    turns=1, kind="other", eligible_local=False)
        args.update(kw)
        return route_cost.estimate(self.pricing, **args)

    def test_tiny_unit_is_direct(self):
        self.assertEqual(self.route()["reasonCode"], "DIRECT_CHEAPER")

    def test_over_caps_is_never_direct(self):
        for over in (dict(read=6_001), dict(output=1_501), dict(turns=5)):
            with self.subTest(**over):
                r = self.route(**over)
                self.assertEqual(r["route"], "FRONTIER_WORKER")
                self.assertEqual(r["reasonCode"], "OVER_DIRECT_CAPS")

    def test_local_route_only_when_enabled(self):
        r = self.route(read=20_000, turns=6, eligible_local=True)
        self.assertEqual(r["route"], "LOCAL_DEFAULT")

    def test_shipped_config_keeps_local_disabled(self):
        routing = json.loads((POLICY_ROOT / "references" / "worker-routing.json").read_text(encoding="utf-8"))
        self.assertIs(routing["local"]["enabled"], False)

    def test_unknown_model_prices_as_default_orchestrator(self):
        self.assertEqual(self.route(model="gpt-9-unknown")["orchestratorModel"], self.pricing["defaultOrchestrator"])


class PolicyLint(unittest.TestCase):
    def test_policy_and_config_lint_clean(self):
        self.assertEqual(lint(), [])


def main() -> int:
    problems = lint()
    if problems:
        print("worker-policy lint failed:")
        for problem in problems:
            print(f"- {problem}")
    else:
        print(f"policy lint ok ({len(REQUIRED_PATTERNS)} patterns, {len(REQUIRED_REFERENCES)} references)")
    tests = unittest.main(argv=[__file__], exit=False).result
    return 0 if not problems and tests.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
