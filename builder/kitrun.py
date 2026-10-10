"""Run the kit's example builder once, isolated and traced, and export what it built.

    .venv/bin/python -m builder.kitrun BRIEF [BRIEF ...] --tools OPENAPI [--label NAME] [--model ID] [--minutes 30] [--skill DIR]

The kit builder (examples/agent_builder.py with its skill build-phone-agent) runs unchanged in a fresh copy of the
kit under runs/<stamp>-<label>/workspace/. Only the given briefs are in workspace/briefs/. The given tool API file
is copied to workspace/tools/openapi.json, where the skill reads it. Freya slot and persona ids are shared through
state/, so a slot is updated in place across runs and the workspace does not fill up.

Claude Code gets its own CLAUDE_CONFIG_DIR and HOME: no personal memory, mods or hooks reach the build.

Output in runs/<stamp>-<label>/: trace.txt (the trace to submit), trace.jsonl (sanitized SDK messages),
summary.json, console.log, one <slot>.workflow.json per workflow the run saved (exported from Freya),
and copies of out/, results/ and every file the builder wrote. Secrets are redacted and the run dir is scanned.
With --skill DIR the given skill replaces the kit's skill in the workspace and tools/check_workflow.py is added.
After the build every exported workflow is checked statically (builder/workflow_check.py), with the builder's
out/<slot>.contract.json when it wrote one.
Exit status: 0 done, 1 builder failed or timed out, 2 a secret was found in the output,
3 an exported workflow has static check errors.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "docs" / "build-the-builder"
STATE = ROOT / "state"
ISOLATED = ROOT / ".claude-builder"
KIT_SKIP = {"env.sh", ".freya-agents.json", ".personas.json", "traces", "results", "out", "briefs", ".DS_Store", "__pycache__"}
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD")


def load_env(path: Path) -> dict[str, str]:
    """`export NAME=value` lines of a shell env file. Comments and blank lines are skipped."""
    env = {}
    for line in path.read_text().splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)$", line)
        if not m:
            continue
        value = m.group(2).split(" #")[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        env[m.group(1)] = value
    return env


REQUIRED_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY")
OPTIONAL_ENV = ("FREYA_API_URL", "FREYA_WORKSPACE_ID", "FREYA_BANK_HOST")


def resolve_env(env_file: Path, environ: dict[str, str]) -> dict[str, str]:
    """Kit settings: env.sh when it exists (local), else the process environment (cloud). env.sh wins per name."""
    env = {k: environ[k] for k in (*REQUIRED_ENV, *OPTIONAL_ENV) if environ.get(k)}
    if env_file.exists():
        env.update(load_env(env_file))
    return env


def secrets_of(env: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in env.items() if SECRET_NAME.search(k) and len(v) >= 8}


def redact(text: str, secrets: dict[str, str]) -> str:
    for name, value in secrets.items():
        text = text.replace(value, f"<redacted:{name}>")
    return text.replace(str(ROOT), "<repo>").replace(str(Path.home()), "~")


def scrub(run_dir: Path, workspace: Path, secrets: dict[str, str]) -> list[str]:
    """Redact secret values in every output file outside the (git-ignored) workspace. Returns the files that had one."""
    leaks = []
    for p in run_dir.rglob("*"):
        if not p.is_file() or p.is_relative_to(workspace):
            continue
        data = p.read_bytes()
        if any(v.encode() in data for v in secrets.values()):
            leaks.append(str(p.relative_to(run_dir)))
            for name, v in secrets.items():
                data = data.replace(v.encode(), f"<redacted:{name}>".encode())
            p.write_bytes(data)
    return leaks


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- trace analysis

def _blocks(record: dict) -> list[dict]:
    return [b for b in record.get("content") or [] if isinstance(b, dict)]


def _purpose(block: dict, workspace: str) -> str:
    if "text" in block:
        return " ".join(block["text"].split())[:140]
    name, args = block.get("name", "?"), block.get("input") or {}
    if name == "Bash":
        return "Bash: " + (args.get("description") or " ".join(str(args.get("command", "")).split()))[:130]
    if "file_path" in args:
        return f"{name}: {str(args['file_path']).replace(workspace + '/', '')}"
    return f"{name}: {json.dumps(args)[:120]}"


def summarize_trace(records: list[dict], arrivals: list[float] | None = None, workspace: str = "") -> dict:
    """Model calls with a one-line purpose, the tests and saves the builder ran, files it wrote, and the result."""
    calls: dict[str, dict] = {}
    tool_uses: dict[str, dict] = {}
    results: dict[str, str] = {}
    final = {}
    for i, rec in enumerate(records):
        kind = rec.get("type")
        if kind == "AssistantMessage":
            call = calls.setdefault(rec.get("message_id") or f"#{i}", {"model": rec.get("model"), "at_s": arrivals[i] if arrivals else None, "blocks": []})
            for b in _blocks(rec):
                if "thinking" in b:
                    continue
                call["blocks"].append(b)
                if "id" in b and "name" in b:
                    tool_uses[b["id"]] = b
        elif kind == "UserMessage":
            for b in _blocks(rec):
                if "tool_use_id" in b:
                    c = b.get("content")
                    results[b["tool_use_id"]] = c if isinstance(c, str) else "\n".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
        elif kind == "ResultMessage":
            final = {k: rec.get(k) for k in ("subtype", "is_error", "num_turns", "duration_ms", "total_cost_usd", "usage", "model_usage")}
    model_calls = [{"n": n, "model": c["model"], "at_s": c["at_s"], "purpose": "; ".join(_purpose(b, workspace) for b in c["blocks"][:3]) or "(reasoning only)"}
                   for n, c in enumerate(calls.values(), 1)]
    tests, saves, written = [], [], []
    for tid, b in tool_uses.items():
        args, out = b.get("input") or {}, results.get(tid, "")
        cmd = str(args.get("command", ""))
        if b.get("name") == "Bash" and re.search(r"python[\w.]*\s+(\S*/)?run_cases\.py\s", cmd):
            m, s = re.search(r"(\d+) / (\d+) passed", out), re.search(r"Last simulation (\S+), status (\w+), (\d+) s", out)
            tests.append({"command": " ".join(cmd.split())[:200], "passed": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None,
                          "simulation_id": s.group(1).rstrip(",") if s else None, "status": s.group(2) if s else None, "seconds": int(s.group(3)) if s else None,
                          "fail_lines": [l.strip() for l in out.splitlines() if l.startswith("FAIL")]})
        if b.get("name") == "Bash" and "save_workflow" in cmd:
            for m in re.finditer(r'"workflow_id": "([^"]+)", "agent_id": "([^"]+)"(?:, "version": (\d+))?', out):
                saves.append({"workflow_id": m.group(1), "agent_id": m.group(2), "version": int(m.group(3)) if m.group(3) else 1})
        if b.get("name") in ("Write", "Edit") and args.get("file_path"):
            written.append(str(args["file_path"]))
    return {"model_calls": model_calls, "tests": tests, "saves": saves, "written": sorted(set(written)), "result": final}


# ---------------------------------------------------------------- run

def make_workspace(run_dir: Path, briefs: list[Path], tools: Path, skill: Path | None = None) -> Path:
    """A fresh copy of the kit. With `skill`, that skill replaces the kit's build-phone-agent skill and the
    workflow checker is added as tools/check_workflow.py. The vendored kit itself is never changed."""
    ws = run_dir / "workspace"
    shutil.copytree(KIT, ws, ignore=lambda d, names: [n for n in names if n in KIT_SKIP])
    if skill:
        target = ws / ".claude" / "skills" / "build-phone-agent"
        shutil.rmtree(target)
        shutil.copytree(skill, target)
        shutil.copy2(Path(__file__).with_name("workflow_check.py"), ws / "tools" / "check_workflow.py")
    (ws / "briefs").mkdir()
    for b in briefs:
        shutil.copy2(b, ws / "briefs" / b.name)
    shutil.copy2(tools, ws / "tools" / "openapi.json")
    STATE.mkdir(exist_ok=True)
    for name, target in ((".freya-agents.json", STATE / "freya-agents.json"), (".personas.json", STATE / "personas.json")):
        if not target.exists():
            target.write_text("{}")
        (ws / name).symlink_to(target)
    return ws


def _tail(path_glob_dir: Path, t0: float, stop: threading.Event, out: list) -> None:
    """Stamp each trace line with the second it appeared. agent_builder.py flushes after every message."""
    pos, f = 0, None
    while not stop.is_set() or f is not None:
        if f is None:
            found = sorted(path_glob_dir.glob("*.jsonl"))
            if found:
                f = found[-1]
            elif stop.is_set():
                return
        if f is not None:
            data = f.read_bytes()[pos:]
            complete = data[: data.rfind(b"\n") + 1]
            pos += len(complete)
            out.extend([round(time.time() - t0, 1)] * complete.count(b"\n"))
            if stop.is_set():
                return
        time.sleep(0.5)


def run(briefs: list[Path], tools: Path, label: str, model: str | None, minutes: float, skill: Path | None = None) -> int:
    if importlib.util.find_spec("claude_agent_sdk") is None:
        sys.exit("claude_agent_sdk is not installed for this Python. Use .venv/bin/python -m builder.kitrun ...")
    env_file = KIT / "env.sh"
    file_env = resolve_env(env_file, dict(os.environ))
    secrets = secrets_of(file_env)
    for need in REQUIRED_ENV:
        if not file_env.get(need):
            sys.exit(f"{need} is missing: set it in {env_file} or in the environment")
    os.environ.update(file_env)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "runs" / f"{stamp}-{label}"
    run_dir.mkdir(parents=True)
    ws = make_workspace(run_dir, briefs, tools, skill)
    state_before = json.loads((STATE / "freya-agents.json").read_text())

    (ISOLATED / "home").mkdir(parents=True, exist_ok=True)
    child_env = {**os.environ, "CLAUDE_CONFIG_DIR": str(ISOLATED), "HOME": str(ISOLATED / "home")}
    if model:
        child_env["BUILDER_MODEL"] = model
    cmd = [sys.executable, "-u", "examples/agent_builder.py", *[f"briefs/{b.name}" for b in briefs]]
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip())

    start = datetime.now(timezone.utc)
    t0 = time.time()
    print(f"run {run_dir.name}: {' '.join(cmd[2:])}  (limit {minutes:g} min)", flush=True)
    proc = subprocess.Popen(cmd, cwd=ws, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    timed_out = threading.Event()
    watchdog = threading.Timer(minutes * 60, lambda: (timed_out.set(), proc.kill()))
    watchdog.start()
    arrivals: list[float] = []
    stop = threading.Event()
    tailer = threading.Thread(target=_tail, args=(ws / "traces", t0, stop, arrivals), daemon=True)
    tailer.start()
    with open(run_dir / "console.log", "w") as log:
        for line in proc.stdout:
            stamped = f"[{int(time.time() - t0) // 60:02d}:{int(time.time() - t0) % 60:02d}] {redact(line.rstrip(), secrets)}"
            print(stamped, flush=True)
            log.write(stamped + "\n")
    code = proc.wait()
    watchdog.cancel()
    stop.set()
    tailer.join(timeout=5)
    end = datetime.now(timezone.utc)

    raw = sorted((ws / "traces").glob("*.jsonl"))
    records = [json.loads(l) for l in raw[-1].read_text().splitlines()] if raw else []
    summary = summarize_trace(records, arrivals if len(arrivals) == len(records) else None, str(ws))
    if raw:
        (run_dir / "trace.jsonl").write_text(redact(raw[-1].read_text(), secrets))

    # What the run created or updated on Freya: slots that are new or whose version moved.
    sys.path.insert(0, str(ws))
    import freya  # noqa: E402  reads FREYA_API_KEY at import, so only after os.environ is set
    state_after = json.loads((STATE / "freya-agents.json").read_text())
    freya_objects = []
    for slot, s in state_after.items():
        if state_before.get(slot) != s:
            path = run_dir / f"{slot}.workflow.json"
            try:
                freya.export_workflow(s["workflow_id"], str(path))
                exported = path.name
            except Exception as e:  # keep the run record even if the export fails
                exported = f"export failed: {e}"
            freya_objects.append({"slot": slot, **s, "created": slot not in state_before, "export": exported})

    checks = check_exports(run_dir, ws, freya_objects, contract_required=skill is not None)

    for sub in ("out", "results"):
        if (ws / sub).exists():
            shutil.copytree(ws / sub, run_dir / sub)
    for i, p in enumerate(summary["written"]):
        src = Path(p) if Path(p).is_absolute() else ws / p
        if src.is_file():
            rel = src.relative_to(ws) if src.is_relative_to(ws) else Path("outside") / f"{i}-{src.name}"
            (run_dir / "written" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, run_dir / "written" / rel)

    res = summary["result"]
    info = {
        "run": run_dir.name, "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
        "seconds": round((end - start).total_seconds()), "limit_minutes": minutes, "timed_out": timed_out.is_set(), "exit_code": code,
        "builder": "docs/build-the-builder/examples/agent_builder.py (unchanged), skill "
                   + (f"{redact(str(skill), {})} (sha256:{sha256(skill / 'SKILL.md')[:12]})" if skill else "build-phone-agent from the kit"),
        "builder_model": model or "claude-opus-5-5 (agent_builder.py default)", "agent_model": freya.AGENT_LLM,
        "repo_commit": commit, "repo_dirty": dirty, "isolation": {"CLAUDE_CONFIG_DIR": "<repo>/.claude-builder", "HOME": "<repo>/.claude-builder/home"},
        "inputs": {"briefs": [{"name": b.name, "sha256": sha256(b)} for b in briefs], "tools": {"name": tools.name, "sha256": sha256(tools)}},
        "freya": freya_objects, "tests": summary["tests"], "written": summary["written"],
        "cost_usd": res.get("total_cost_usd"), "num_turns": res.get("num_turns"), "model_usage": res.get("model_usage"),
        "model_calls": summary["model_calls"], "checks": checks,
    }
    (run_dir / "summary.json").write_text(redact(json.dumps(info, indent=1, default=str), secrets))
    (run_dir / "trace.txt").write_text(redact(render_trace(info), secrets))

    leaks = scrub(run_dir, ws, secrets)
    print(f"\n{render_result(info)}\noutput: {run_dir.relative_to(ROOT)}", flush=True)
    if leaks:
        print(f"SECRET FOUND and redacted in {leaks}. Check how it got there before using this run.", file=sys.stderr)
        return 2
    if code != 0 or timed_out.is_set():
        return 1
    return 3 if any(c["errors"] for c in checks) else 0


def check_exports(run_dir: Path, ws: Path, freya_objects: list[dict], contract_required: bool = False) -> list[dict]:
    """Static checks of every exported workflow against the run's tool API, with the builder's contract if it wrote one.

    Fails closed: a run that saved nothing, a missing export, and (when the skill requires one) a missing or unreadable
    contract are errors, so they cannot pass as a clean check."""
    from .workflow_check import check
    if not freya_objects:
        return [{"slot": "(none)", "contract": None, "errors": ["the run saved no workflow on Freya"], "warnings": 0}]
    api = json.loads((ws / "tools" / "openapi.json").read_text())
    out = []
    for f in freya_objects:
        entry = {"slot": f["slot"], "contract": None, "errors": [], "warnings": 0}
        out.append(entry)
        path = run_dir / f"{f['slot']}.workflow.json"
        if not path.is_file():
            entry["errors"].append("no export of this workflow, so it was not checked")
            continue
        cpath = ws / "out" / f"{f['slot']}.contract.json"
        contract = None
        if cpath.is_file():
            try:
                contract = json.loads(cpath.read_text())
                entry["contract"] = cpath.name
            except ValueError as e:
                entry["errors"].append(f"{cpath.name} is not valid JSON: {e}")
        elif contract_required:
            entry["errors"].append(f"{cpath.name} is missing, so terminal-tool ordering could not be checked")
        found = check(json.loads(path.read_text()), api, contract, ws)
        entry["errors"] += [str(x) for x in found if x.level == "error"]
        entry["warnings"] = sum(x.level == "warning" for x in found)
    return out


def render_result(info: dict) -> str:
    tests = ", ".join(f"{t['passed']}/{t['total']}" for t in info["tests"]) or "none"
    cost = info["cost_usd"]
    return (f"{info['seconds']} s, cost {'$%.2f' % cost if cost is not None else 'unknown'}, builder tests: {tests}, "
            f"exit {info['exit_code']}{', TIMED OUT' if info['timed_out'] else ''}")


def render_trace(info: dict) -> str:
    """Plain-text trace: start and end, every model call with a one-line purpose, what was created on Freya, tests."""
    L = [f"Freya builder trace: {info['run']}",
         f"start {info['start']}  end {info['end']}  ({info['seconds']} s, limit {info['limit_minutes']:g} min{', TIMED OUT' if info['timed_out'] else ''})",
         f"builder: {info['builder']}; model {info['builder_model']}",
         f"phone agent model: {info['agent_model']['provider']}/{info['agent_model']['model']} (set by freya.py)",
         f"repo commit {info['repo_commit']}{' (uncommitted changes)' if info['repo_dirty'] else ''}",
         "inputs: " + ", ".join(f"{b['name']} sha256:{b['sha256'][:12]}" for b in info["inputs"]["briefs"]) + f"; tools {info['inputs']['tools']['name']} sha256:{info['inputs']['tools']['sha256'][:12]}",
         "", f"model calls ({len(info['model_calls'])} in the message log):"]
    for c in info["model_calls"]:
        at = f"+{int(c['at_s']) // 60:02d}:{int(c['at_s']) % 60:02d}" if c["at_s"] is not None else "      "
        L.append(f"  {c['n']:03d} {at} {c['model']}: {c['purpose']}")
    for model, u in (info["model_usage"] or {}).items():
        L.append(f"  totals {model}: in {u.get('inputTokens')} out {u.get('outputTokens')} cache-read {u.get('cacheReadInputTokens')} "
                 f"cache-write {u.get('cacheCreationInputTokens')} cost ${u.get('costUSD', 0):.4f}"
                 + ("" if any(c["model"] == model for c in info["model_calls"]) else "  (Claude Code's own helper calls, not in the message log)"))
    L += ["", "created or updated on Freya:"]
    L += [f"  slot {f['slot']}: workflow {f['workflow_id']}, agent {f['agent_id']}, version {f.get('version', 1)}, "
          f"{'created' if f['created'] else 'updated'}, exported to {f['export']}" for f in info["freya"]] or ["  nothing"]
    L += ["", "tests the builder ran on its agent:"]
    for i, t in enumerate(info["tests"], 1):
        L.append(f"  {i}. {t['command']}\n     {t['passed']} / {t['total']} passed, simulation {t['simulation_id']} {t['status']}, {t['seconds']} s")
        L += [f"     {l}" for l in t["fail_lines"]]
    if not info["tests"]:
        L.append("  none")
    L += ["", "static checks of the exported workflows (graph properties only, not runtime behaviour):"]
    for c in info.get("checks") or []:
        L.append(f"  {c['slot']}: {len(c['errors'])} errors, {c['warnings']} warnings, "
                 + (f"contract {c['contract']}" if c["contract"] else "no contract, so terminal-tool ordering was not checked"))
        L += [f"     {e}" for e in c["errors"]]
    L += ["", f"files the builder wrote: {', '.join(info['written']) or 'none'}", f"result: {render_result(info)}", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m builder.kitrun", description=__doc__.split("\n\n")[0])
    p.add_argument("briefs", nargs="+", type=Path)
    p.add_argument("--tools", type=Path, required=True, help="the brief's tool API file (OpenAPI JSON)")
    p.add_argument("--label", default="kit", help="suffix of the run directory name")
    p.add_argument("--model", help="builder model (BUILDER_MODEL); default: agent_builder.py's own default")
    p.add_argument("--minutes", type=float, default=30, help="hard time limit for the whole build (default 30)")
    p.add_argument("--skill", type=Path, help="skill directory that replaces the kit's build-phone-agent skill in the workspace")
    a = p.parse_args(argv)
    for f in [*a.briefs, a.tools]:
        if not f.is_file():
            p.error(f"no such file: {f}")
    if a.skill and not (a.skill / "SKILL.md").is_file():
        p.error(f"no SKILL.md in {a.skill}")
    return run([b.resolve() for b in a.briefs], a.tools.resolve(), a.label, a.model, a.minutes, a.skill.resolve() if a.skill else None)


if __name__ == "__main__":
    sys.exit(main())
