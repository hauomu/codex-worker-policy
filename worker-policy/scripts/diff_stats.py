"""Measure a worker's diff and say whether it needs a cleanup pass.

Cheap and deterministic (git only, no model call), so the orchestrator runs it itself after
an implementation unit instead of reading the diff. Untracked files count as added lines.

Prints one line, e.g.
  DIFF added=412 removed=37 files=6 new_files=3 budget=200 comment_ratio=0.21 debug_markers=2 status=CLEANUP_RECOMMENDED reasons=over_budget,debug_markers

status is CLEAN or CLEANUP_RECOMMENDED. Reasons: over_budget (added lines above the unit's
budget), comment_heavy (added comment lines above maxCommentRatio), debug_markers (new
print-debugging, breakpoints or TODO/FIXME/XXX lines).

Usage:
  python diff_stats.py --repo <path> --base <commit-before-the-unit> [--budget 150] [--json]
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTING = os.path.join(HERE, "..", "references", "worker-routing.json")

COMMENT = re.compile(r"^\s*(#|//|/\*|\*|--|;|<!--)")
DEBUG = re.compile(r"console\.(log|debug)\(|\bdebugger;|\bbreakpoint\(\)|pdb\.set_trace|\bdbg!\(|"
                   r"print\(\s*f?[\"'](DEBUG|debug|>>>|here)")
TODO = re.compile(r"\b(TODO|FIXME|XXX)\b")  # counted only on comment lines


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def added_lines(repo, base):
    """Yield (path, line) for every added line, tracked or untracked."""
    path = None
    for line in git(repo, "diff", "--no-color", "--no-ext-diff", "-U0", base).splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and path:
            yield path, line[1:]
    for path in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        try:
            with open(os.path.join(repo, path), encoding="utf-8") as fh:
                for line in fh:
                    yield path, line.rstrip("\n")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: counted as a new file only


def measure(repo, base, budget, max_comment_ratio):
    removed, files = 0, set()
    for row in git(repo, "diff", "--numstat", base).splitlines():
        a, r, path = row.split("\t", 2)
        files.add(path)
        removed += int(r) if r.isdigit() else 0
    new_files = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    new_files += git(repo, "diff", "--name-only", "--diff-filter=A", base).splitlines()
    added = comments = markers = 0
    for path, line in added_lines(repo, base):
        files.add(path)
        if not line.strip():
            continue
        added += 1
        is_comment = bool(COMMENT.match(line))
        comments += is_comment
        markers += bool(DEBUG.search(line) or (is_comment and TODO.search(line)))
    ratio = comments / added if added else 0.0
    reasons = [name for name, hit in (("over_budget", added > budget),
                                      ("comment_heavy", added >= 20 and ratio > max_comment_ratio),
                                      ("debug_markers", markers > 0)) if hit]
    return {"added": added, "removed": removed, "files": len(files), "newFiles": len(set(new_files)),
            "budget": budget, "commentRatio": round(ratio, 2), "debugMarkers": markers,
            "status": "CLEANUP_RECOMMENDED" if reasons else "CLEAN", "reasons": reasons}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".", help="repository the worker changed")
    ap.add_argument("--base", required=True, help="commit (or ref) from before the unit started")
    ap.add_argument("--budget", type=int, help="expected added lines for the unit (default: worker-routing.json)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(ROUTING, encoding="utf-8") as fh:
        cfg = json.load(fh).get("cleanup") or {}
    budget = a.budget if a.budget is not None else int(cfg.get("defaultBudgetLines", 200))
    try:
        r = measure(a.repo, a.base, budget, float(cfg.get("maxCommentRatio", 0.35)))
    except subprocess.CalledProcessError as error:
        print(f"DIFF status=ERROR detail={error.stderr.strip()[:200]!r}")
        return 2
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"DIFF added={r['added']} removed={r['removed']} files={r['files']} new_files={r['newFiles']} "
              f"budget={r['budget']} comment_ratio={r['commentRatio']} debug_markers={r['debugMarkers']} "
              f"status={r['status']}" + (f" reasons={','.join(r['reasons'])}" if r["reasons"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
