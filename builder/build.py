"""The final's run command: python3 builder/build.py CASE_FOLDER MOCK_URL [--skill DIR] [--label NAME] [--minutes N]

1. Convert the case folder's documents into files the builder can read (builder/docs_text.py). They go to
   runs/inputs-<stamp>-<label>/briefs/, with a manifest of every source file and its sha256.
2. Read the tool API from MOCK_URL/openapi.json. The tools call the mock, so the mock's own description is the API.
   Write a copy whose `servers` is MOCK_URL only. The workflow checker then rejects a tool URL outside the mock
   (E-TOOL-SERVER).
3. Run builder.kitrun on those files: isolated, traced, with a fresh --state and its time limit.
4. Check every URL in the exported workflows against MOCK_URL.

This script does not read what the documents say. Exit: kitrun's exit code, or 4 when an exported URL is outside
the mock."""
import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.docs_text import convert  # noqa: E402


def under(url: str, base: str) -> bool:
    """Same scheme and host as `base`, and a path at or below its path (not a mere string prefix)."""
    u, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
    path, root = u.path or "/", b.path.rstrip("/")
    return (u.scheme.lower(), u.netloc.lower()) == (b.scheme.lower(), b.netloc.lower()) \
        and (root == "" or path == root or path.startswith(root + "/"))


def urls_in(obj):
    if isinstance(obj, (dict, list)):
        for v in obj.values() if isinstance(obj, dict) else obj:
            yield from urls_in(v)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        yield obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("case", type=Path)
    p.add_argument("mock_url")
    p.add_argument("--skill", type=Path, default=ROOT / "builder/skills/reference")
    p.add_argument("--label", default="final")
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--prepare-only", action="store_true", help="convert the inputs and write the tool API, then stop")
    a = p.parse_args()
    mock = a.mock_url.rstrip("/")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    inputs = ROOT / "runs" / f"inputs-{stamp}-{a.label}"
    manifest = convert(a.case.resolve(), inputs / "briefs")
    skipped = [f for f in manifest["files"] if f.get("skipped")]
    for f in skipped:
        print(f"build.py: not converted: {f['source']}: {f['skipped']}", file=sys.stderr)

    # Cloudflare answers 403 (error 1010) to urllib's default User-Agent on workers.dev.
    req = urllib.request.Request(f"{mock}/openapi.json", headers={"User-Agent": "freya-builder-build/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        api = json.loads(r.read().decode("utf-8"))
    manifest["tool_api"] = f"{mock}/openapi.json"
    api["servers"] = [{"url": mock}]
    tools = inputs / "openapi.json"
    tools.write_text(json.dumps(api, indent=1, ensure_ascii=False), encoding="utf-8")
    manifest["mock_url"] = mock
    (inputs / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    briefs = sorted((inputs / "briefs").iterdir())
    if a.prepare_only:
        print(f"build.py: prepared {inputs.relative_to(ROOT)}: {len(briefs)} files, tool API from {manifest['tool_api']}, {len(api.get('paths') or {})} paths")
        return 0
    state = ROOT / "state" / f"final-{a.label}-{stamp}"
    py = ROOT / ".venv/bin/python"
    opts = ["--tools", str(tools), "--label", a.label, "--skill", str(a.skill.resolve()), "--state", str(state),
            "--minutes", str(a.minutes)]
    print("build.py: -m builder.kitrun", f"<{len(briefs)} files>", " ".join(opts), flush=True)
    code = subprocess.call([str(py if py.exists() else sys.executable), "-m", "builder.kitrun", *map(str, briefs), *opts],
                           cwd=ROOT)

    runs = sorted((r for r in ROOT.glob(f"runs/*-{a.label}") if not r.name.startswith("inputs-")),
                  key=lambda r: r.stat().st_mtime)
    run = runs[-1] if runs else None
    if run and (run / "summary.json").is_file():
        s = json.loads((run / "summary.json").read_text())
        bad, exports = [], 0
        for f in s.get("freya") or []:
            exp = run / str(f.get("export"))
            if exp.is_file():
                exports += 1
                bad += [u for u in urls_in(json.loads(exp.read_text())) if not under(u, mock)]
        print(f"build.py: run {run.relative_to(ROOT)}, inputs {inputs.relative_to(ROOT)}, state {state.relative_to(ROOT)}")
        if bad:
            print(f"build.py: {len(bad)} URL(s) in the export are outside {mock}: {sorted(set(bad))[:5]}", file=sys.stderr)
            return code or 4
        print(f"build.py: every URL in {exports} export(s) is under {mock}" if exports else "build.py: no export")
    return code


if __name__ == "__main__":
    sys.exit(main())
