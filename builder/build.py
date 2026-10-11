"""The final's run command: python3 builder/build.py CASE_FOLDER MOCK_URL [--skill DIR] [--label NAME] [--minutes N]

1. Turns the case folder's documents into files the builder can read (builder/docs_text.py), under
   runs/inputs-<stamp>-<label>/briefs/, with a manifest of every source file and its sha256.
2. Finds the tool API: an OpenAPI JSON file in the case folder, else MOCK_URL/openapi.json (the mock may publish
   its own). Writes a copy whose `servers` is MOCK_URL only, so the workflow checker rejects any tool URL outside
   the mock (E-TOOL-SERVER).
3. Runs builder.kitrun on those files: isolated, traced, with a fresh --state and its time limit.
4. Checks every URL in the exported workflows against MOCK_URL.

Nothing here knows what the documents say. Exit: kitrun's exit code, or 4 when an exported URL is outside the mock."""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.docs_text import convert  # noqa: E402


def find_openapi(case: Path) -> Path | None:
    for p in sorted(case.rglob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and ("openapi" in d or "swagger" in d) and isinstance(d.get("paths"), dict):
            return p
    return None


def urls_in(obj, out: list[str]) -> list[str]:
    if isinstance(obj, dict):
        for v in obj.values():
            urls_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            urls_in(v, out)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        out.append(obj)
    return out


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

    src = find_openapi(a.case)
    if src:
        api = json.loads(src.read_text(encoding="utf-8"))
        manifest["tool_api"] = {"source": str(src.relative_to(a.case)), "from": "case folder"}
    else:
        with urllib.request.urlopen(f"{mock}/openapi.json", timeout=30) as r:
            api = json.loads(r.read().decode("utf-8"))
        manifest["tool_api"] = {"source": f"{mock}/openapi.json", "from": "mock"}
    api["servers"] = [{"url": mock}]
    tools = inputs / "openapi.json"
    tools.write_text(json.dumps(api, indent=1, ensure_ascii=False), encoding="utf-8")
    manifest["mock_url"] = mock
    (inputs / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    briefs = sorted((inputs / "briefs").iterdir())
    if a.prepare_only:
        print(f"build.py: prepared {inputs.relative_to(ROOT)}: {len(briefs)} files, tool API from {manifest['tool_api']['source']}, {len(api.get('paths') or {})} paths")
        return 0
    state = ROOT / "state" / f"final-{a.label}-{stamp}"
    py = ROOT / ".venv/bin/python"
    cmd = [str(py if py.exists() else sys.executable), "-m", "builder.kitrun", *map(str, briefs), "--tools", str(tools),
           "--label", a.label, "--skill", str(a.skill.resolve()), "--state", str(state), "--minutes", str(a.minutes)]
    print("build.py:", " ".join(cmd[:3]), f"<{len(briefs)} files>", " ".join(cmd[3 + len(briefs):]), flush=True)
    code = subprocess.call(cmd, cwd=ROOT)

    runs = sorted(ROOT.glob(f"runs/*-{a.label}"), key=lambda r: r.stat().st_mtime)
    run = runs[-1] if runs else None
    if run and (run / "summary.json").is_file():
        s = json.loads((run / "summary.json").read_text())
        bad = []
        for f in s.get("freya") or []:
            exp = run / str(f.get("export"))
            if exp.is_file():
                bad += [u for u in urls_in(json.loads(exp.read_text()), []) if not u.startswith(mock)]
        print(f"build.py: run {run.relative_to(ROOT)}, inputs {inputs.relative_to(ROOT)}, state {state.relative_to(ROOT)}")
        if bad:
            print(f"build.py: {len(bad)} URL(s) in the export are outside {mock}: {sorted(set(bad))[:5]}", file=sys.stderr)
            return code or 4
        print(f"build.py: every URL in the export is under {mock}")
    return code


if __name__ == "__main__":
    sys.exit(main())
