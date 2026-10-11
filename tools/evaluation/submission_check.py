"""Check the final submission against the committed repository. Read-only.

    python3 -I tools/evaluation/submission_check.py REPO SUBMISSION_JSON

Checks, each printed PASS or FAIL:
- submission.json has the fields of the case BRIEF, in that order.
- The workflow and the trace exist at the named commit, and the committed workflow is byte-identical to the export
  whose sha256 the run's summary.json recorded.
- Every URL in the workflow is under mock_url.
- The run's commit (summary.json repo_commit) is an ancestor of the named commit, and nothing under builder/ or
  docs/build-the-builder/ changed between them.
- The skill in run_command is the skill the run used (sha256 prefix in summary.json), at the named commit.
Exit 1 when a check fails."""
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

FIELDS = ["team", "members", "repo", "commit", "run_command", "workflow", "trace", "mock_url"]
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""))


def git(repo: Path, *args: str, binary: bool = False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    return r.returncode, (r.stdout if binary else r.stdout.decode("utf-8", "replace").strip())


def urls(obj):
    if isinstance(obj, (dict, list)):
        for v in obj.values() if isinstance(obj, dict) else obj:
            yield from urls(v)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        yield obj


def under(url: str, base: str) -> bool:
    u, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
    root = b.path.rstrip("/")
    return (u.scheme, u.netloc.lower()) == (b.scheme, b.netloc.lower()) and (not root or u.path == root or u.path.startswith(root + "/"))


def main() -> int:
    repo, sub_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    sub = json.loads(sub_path.read_text(encoding="utf-8"))
    check("submission fields", list(sub) == FIELDS, ", ".join(sub))
    check("members", bool(sub["members"]) and all(set(m) == {"name", "email"} and m["email"] for m in sub["members"]))
    commit = sub["commit"]
    # Values from submission.json reach git as arguments: only a hex commit and plain relative paths are accepted.
    safe = re.fullmatch(r"[0-9a-f]{7,40}", str(commit)) and all(
        isinstance(sub[k], str) and not sub[k].startswith(("-", "/")) and ".." not in Path(sub[k]).parts for k in ("workflow", "trace"))
    check("commit and paths are plain values", bool(safe))
    if not safe:
        return 1
    code, full = git(repo, "rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}")
    check("commit exists", code == 0, full)
    if code:
        return 1
    code, _ = git(repo, "merge-base", "--is-ancestor", commit, "origin/builder-integration")
    check("commit is pushed (on origin/builder-integration)", code == 0)

    for key in ("workflow", "trace"):
        code, _ = git(repo, "cat-file", "-e", f"{full}:{sub[key]}")
        check(f"{key} at the commit", code == 0, sub[key])
    run_dir = str(Path(sub["workflow"]).parent)
    code, summary = git(repo, "show", f"{full}:{run_dir}/summary.json")
    check("summary.json at the commit", code == 0)
    if code:
        return 1
    s = json.loads(summary)
    _, wf_bytes = git(repo, "show", f"{full}:{sub['workflow']}", binary=True)
    slot = next((f for f in s.get("freya") or [] if f.get("export") == Path(sub["workflow"]).name), None)
    check("workflow is the run's export (sha256)", bool(slot) and hashlib.sha256(wf_bytes).hexdigest() == slot.get("export_sha256"),
          slot and slot.get("export_sha256", "")[:12])
    bad = sorted({u for u in urls(json.loads(wf_bytes)) if not under(u, sub["mock_url"])})
    check("every workflow URL is under mock_url", not bad, ", ".join(bad[:3]))
    acc = s.get("acceptance") or {}
    print(f"INFO run acceptance: accepted={acc.get('accepted')} exit={acc.get('exit')} seconds={acc.get('seconds_total')}")
    secs = acc.get("seconds_total")
    check("run within 30 minutes", isinstance(secs, (int, float)) and secs <= 1800 and s.get("timed_out") is False, str(secs))

    run_commit = s.get("repo_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", run_commit):
        check("run commit recorded", False, run_commit)
        return 1
    code, _ = git(repo, "merge-base", "--is-ancestor", run_commit, full)
    check("run commit is an ancestor of the named commit", code == 0, run_commit[:12])
    _, changed = git(repo, "diff", "--name-only", run_commit, full, "--", "builder", "docs/build-the-builder")
    check("builder unchanged between run and named commit", changed == "", changed.replace("\n", ", "))
    check("run started on a clean tree", s.get("repo_dirty") is False)

    m = re.search(r"--skill\s+(\S+)", sub["run_command"])
    used = re.search(r"skill <repo>/(\S+) \(sha256:([0-9a-f]+)\)", s.get("builder", ""))
    ok = bool(m and used and m.group(1).rstrip("/") == used.group(1).rstrip("/"))
    if ok:
        _, skill = git(repo, "show", f"{full}:{m.group(1).rstrip('/')}/SKILL.md", binary=True)
        ok = hashlib.sha256(skill).hexdigest().startswith(used.group(2))
    check("run_command skill = the run's skill (sha256)", ok, m.group(1) if m else "no --skill")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
