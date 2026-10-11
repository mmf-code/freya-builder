"""Run the kit's example builder once, isolated and traced, and export what it built.

    .venv/bin/python -m builder.kitrun BRIEF [BRIEF ...] --tools OPENAPI [--label NAME] [--model ID] [--minutes 30] [--skill DIR] [--state DIR]

The kit builder (examples/agent_builder.py with its skill build-phone-agent) runs unchanged in a fresh copy of the
kit under runs/<stamp>-<label>/workspace/. Only the given briefs are in workspace/briefs/, and public-test-set.json
holds only the practice customers of kit briefs identical to an input brief (none for a hidden brief). The given tool API file
is copied to workspace/tools/openapi.json, where the skill reads it. Freya slot and persona ids are shared through
state/, so a slot is updated in place across runs and the workspace does not fill up.

Claude Code gets its own CLAUDE_CONFIG_DIR and HOME: no personal memory, mods or hooks reach the build.

Output in runs/<stamp>-<label>/: trace.txt (the trace to submit), trace.jsonl (sanitized SDK messages),
summary.json, console.log, one <slot>.workflow.json per workflow the run saved (exported from Freya),
and copies of out/, results/ and every file the builder wrote. Secrets are redacted and the run dir is scanned.
With --skill DIR the given skill replaces the kit's skill in the workspace and tools/check_workflow.py,
tools/lower.py and tools/dryrun.py are added. With --state DIR the run keeps its slot and persona ids there instead of state/, so it can
neither update another run's workflows nor share its personas.
After the build every exported workflow is checked statically (builder/workflow_check.py), with the builder's
out/<slot>.contract.json when it wrote one, against the tool API and brief files as the runner read them into memory
before the build (not the workspace copies, not the files on disk afterwards). The trace is read through the file
handle the runner opened when agent_builder.py created it, and its SDK result is cross-checked with the "done:" line
agent_builder.py printed to the runner's pipe. A run is accepted only when the builder exited 0 with that confirmed
successful SDK result, within the time limit counted up to the end of the export and checks, with every input file and
the trace unchanged, and with no check error.
Threat model: these checks catch accidents (an SDK error result, a crashed or stopped builder, a stray or edited file)
and make a forged success hard; they are not authentication. The builder runs as the same user with Bash and no
sandbox, and its own text reaches the same pipe, so a builder that set out to forge both the trace and the "done:" line
could. Containing that needs OS-level isolation of the builder, which would change what the builder can do. Nothing is deleted when a
run is rejected; summary.json and trace.txt give the reasons under "acceptance".
Exit status: 0 accepted, 1 builder failed, SDK error, timed out or over the limit, 2 a secret was found in the output,
3 a check failed (static errors, missing export or contract, contract without a terminal tool, changed input).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "docs" / "build-the-builder"
STATE = ROOT / "state"
ISOLATED = ROOT / ".claude-builder"
KIT_SKIP = {"env.sh", ".freya-agents.json", ".personas.json", "traces", "results", "out", "briefs", "public-test-set.json", ".DS_Store", "__pycache__"}
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


# ---------------------------------------------------------------- acceptance (outside the builder's view)

def input_manifest(briefs: list[Path], tools: Path) -> dict[str, dict]:
    """Workspace path -> source file, bytes and sha256 of every input, each read once before the build starts. The
    bytes stay in the runner's memory: the checks after the build use them, not a file the builder could reach."""
    m = {}
    for rel, path in [*((f"briefs/{b.name}", b) for b in briefs), ("tools/openapi.json", tools)]:
        data = path.read_bytes()
        m[rel] = {"source": path, "data": data, "sha256": hashlib.sha256(data).hexdigest()}
    return m


def input_changes(manifest: dict[str, dict], ws: Path, sources: bool = True) -> list[str]:
    """Inputs whose copy under `ws` (or, with `sources`, whose original file) no longer has the hash taken at the start."""
    out = []
    for rel, m in manifest.items():
        for where, path in (("copy in " + ws.name, ws / rel), *((("source", Path(m["source"])),) if sources else ())):
            if not path.is_file():
                out.append(f"{rel}: {where} is missing")
            elif sha256(path) != m["sha256"]:
                out.append(f"{rel}: {where} changed during the run")
    return out


def pristine_inputs(manifest: dict[str, dict], into: Path) -> Path:
    """The inputs as read at the start, written at their workspace paths (for the checker's own quote check; the
    runner's authoritative quote check uses the bytes in memory)."""
    for rel, m in manifest.items():
        (into / rel).parent.mkdir(parents=True, exist_ok=True)
        (into / rel).write_bytes(m["data"])
    return into


def console_confirms(lines: list[str], trace: Path | None, records: list[dict]) -> str | None:
    """agent_builder.py prints 'done: N turns, S s, $C. Trace: <file>' when it receives the SDK result. A missing or
    different line means the trace's result is not confirmed. Lines after it (warnings on exit) do not matter.
    A consistency check, not authentication: agent_builder.py also prints the model's text to this pipe, so a builder
    that deliberately wrote such a line, together with a forged trace record, would pass it."""
    last = records[-1] if records and records[-1].get("type") == "ResultMessage" else None
    if last is None or trace is None:
        return None                                 # sdk_outcome already rejects the run
    secs = f"{(last.get('duration_ms') or 0) / 1000:.0f}"
    named = [m for m in (re.match(r"\s*done: (\d+) turns, (\d+) s, .*Trace: (\S+)\s*$", line) for line in lines)
             if m and m.group(3).endswith("/" + trace.name)]
    if any(int(m.group(1)) == last.get("num_turns") and m.group(2) == secs for m in named):
        return None
    if named:
        return "agent_builder.py's 'done:' line does not match the trace's SDK result"
    return "agent_builder.py printed no 'done:' line for the trace, so its SDK result is not confirmed"


def final_result(records: list[dict]) -> dict:
    """The SDK result, only when it is the trace's last record: agent_builder.py writes it after the builder's last
    action, so a ResultMessage line the builder wrote into the file earlier cannot stand in for a missing one."""
    if records and records[-1].get("type") == "ResultMessage":
        return {k: records[-1].get(k) for k in ("subtype", "is_error")}
    return {}


def unexpected_traces(ws: Path, trace: Path | None) -> list[str]:
    """Trace files the runner did not watch from the start: the builder could have written them."""
    if trace is None:
        return ["the builder wrote no trace file"]
    return [f"traces/{p.name} was not written by the builder runner" for p in sorted((ws / "traces").glob("*.jsonl")) if p != trace]


def sdk_outcome(result: dict) -> str | None:
    """Why the SDK's final result is not a success, or None. A missing final result is not a success."""
    if not result:
        return "the builder gave no final SDK result"
    if result.get("is_error") or result.get("subtype") != "success":
        return f"the builder's SDK result is an error (subtype {result.get('subtype')!r}, is_error {result.get('is_error')!r})"
    return None


def accept(code: int, timed_out: bool, sdk_reason: str | None, seconds_total: float, limit_s: float,
           checks: list[dict], input_problems: list[str]) -> tuple[int, list[str]]:
    """The run's exit status and every reason it is not accepted. 1 outranks 3; 0 only with no reason at all."""
    fail, bad = [], []
    if timed_out:
        fail.append("the builder was stopped at the time limit")
    if code != 0:
        fail.append(f"the builder exited with status {code}")
    if sdk_reason:
        fail.append(sdk_reason)
    if seconds_total > limit_s:
        fail.append(f"build, export and checks took {seconds_total:.0f} s, over the limit of {limit_s:.0f} s")
    bad += [f"input changed: {x}" for x in input_problems]
    bad += [f"{c['slot']}: {e}" for c in checks for e in c["errors"]]
    return (1 if fail else 3 if bad else 0), fail + bad


def kill_group(proc: subprocess.Popen, grace: float = 5.0) -> None:
    """Stop the builder and every process it started (they share its process group), politely first."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
        if sig == signal.SIGTERM:
            time.sleep(0.2)


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

def practice_cases(briefs: list[Path]) -> list[dict]:
    """The practice customers a build may see and test on: those of a kit brief whose text is identical to an input brief.

    A brief the kit does not contain (a hidden brief, or a rewritten one) gets none. Its agent can then not be tested
    against, or tuned to, another brief's customers and expected outcomes."""
    inputs = {sha256(b) for b in briefs}
    tags = {p.stem.rsplit("-", 1)[-1].upper() for p in (KIT / "briefs").glob("*.md") if sha256(p) in inputs}
    return [c for c in json.loads((KIT / "public-test-set.json").read_text()) if c.get("brief") in tags]


def make_workspace(run_dir: Path, briefs: list[Path], tools: Path, skill: Path | None = None, state: Path = STATE) -> Path:
    """A fresh copy of the kit. With `skill`, that skill replaces the kit's build-phone-agent skill, and the
    workflow checker, the closing lowering and the dry-run tool are added as tools/check_workflow.py, tools/lower.py
    and tools/dryrun.py. The vendored kit itself is never changed."""
    ws = run_dir / "workspace"
    shutil.copytree(KIT, ws, ignore=lambda d, names: [n for n in names if n in KIT_SKIP])
    if skill:
        target = ws / ".claude" / "skills" / "build-phone-agent"
        shutil.rmtree(target)
        shutil.copytree(skill, target)
        shutil.copy2(Path(__file__).with_name("workflow_check.py"), ws / "tools" / "check_workflow.py")
        shutil.copy2(Path(__file__).with_name("lower.py"), ws / "tools" / "lower.py")
        shutil.copy2(Path(__file__).with_name("dryrun.py"), ws / "tools" / "dryrun.py")
    (ws / "briefs").mkdir()
    for b in briefs:
        shutil.copy2(b, ws / "briefs" / b.name)
    shutil.copy2(tools, ws / "tools" / "openapi.json")
    (ws / "public-test-set.json").write_text(json.dumps(practice_cases(briefs), indent=1))
    state.mkdir(parents=True, exist_ok=True)
    for name, target in ((".freya-agents.json", state / "freya-agents.json"), (".personas.json", state / "personas.json")):
        if not target.exists():
            target.write_text("{}")
        (ws / name).symlink_to(target)
    return ws


class WatchedTrace:
    """agent_builder.py's trace file, held open from the moment it appears (the script opens it before the model runs).
    Reading through this handle gets what agent_builder.py wrote even if the path is later replaced, and `seen` keeps
    every complete line already read, so a rewrite of earlier lines shows."""

    def __init__(self, path: Path):
        self.path, self.fh, self.seen = path, open(path, "rb"), bytearray()

    def read_new(self) -> bytes:
        self.fh.seek(len(self.seen))
        data = self.fh.read()
        complete = data[: data.rfind(b"\n") + 1]
        self.seen += complete
        return complete

    def finish(self) -> tuple[str, list[str]]:
        """The whole trace as written to the watched file, and what is wrong with it."""
        self.fh.seek(0)
        data = self.fh.read()
        problems = []
        if not data.startswith(bytes(self.seen)):
            problems.append("lines of the trace changed after they were written")
        try:
            now, held = os.stat(self.path), os.fstat(self.fh.fileno())
            if (now.st_ino, now.st_dev) != (held.st_ino, held.st_dev):
                problems.append(f"traces/{self.path.name} was replaced during the run; the watched file was used")
        except FileNotFoundError:
            problems.append(f"traces/{self.path.name} was removed during the run; the watched file was used")
        self.fh.close()
        return data.decode(errors="replace"), problems


def _tail(path_glob_dir: Path, t0: float, stop: threading.Event, out: list, chosen: list | None = None) -> None:
    """Stamp each trace line with the second it appeared. agent_builder.py flushes after every message.
    The first trace file to appear is agent_builder.py's own; `chosen` gets it as a WatchedTrace."""
    w = None
    while not stop.is_set() or w is not None:
        if w is None:
            found = sorted(path_glob_dir.glob("*.jsonl"))
            if found:
                w = WatchedTrace(found[-1])
                if chosen is not None:
                    chosen.append(w)
            elif stop.is_set():
                return
        if w is not None:
            out.extend([round(time.time() - t0, 1)] * w.read_new().count(b"\n"))
            if stop.is_set():
                return
        time.sleep(0.5)


def run(briefs: list[Path], tools: Path, label: str, model: str | None, minutes: float, skill: Path | None = None, state: Path = STATE) -> int:
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
    manifest = input_manifest(briefs, tools)
    ws = make_workspace(run_dir, briefs, tools, skill, state)
    state_before = json.loads((state / "freya-agents.json").read_text())
    print(f"state {redact(str(state), {})}: slots {sorted(state_before) or 'none'}, "
          f"personas {len(json.loads((state / 'personas.json').read_text()))}", flush=True)

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
    # Own process group: at the limit the builder and everything it started (Claude Code, Bash, tests) are stopped.
    proc = subprocess.Popen(cmd, cwd=ws, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                            start_new_session=True)
    timed_out = threading.Event()
    console: list[str] = []
    watchdog = threading.Timer(minutes * 60, lambda: (timed_out.set(), kill_group(proc)))
    watchdog.start()
    arrivals: list[float] = []
    chosen: list[WatchedTrace] = []
    stop = threading.Event()
    tailer = threading.Thread(target=_tail, args=(ws / "traces", t0, stop, arrivals, chosen), daemon=True)
    tailer.start()
    try:
        with open(run_dir / "console.log", "w") as log:
            for line in proc.stdout:
                console.append(line.rstrip())
                stamped = f"[{int(time.time() - t0) // 60:02d}:{int(time.time() - t0) % 60:02d}] {redact(line.rstrip(), secrets)}"
                print(stamped, flush=True)
                log.write(stamped + "\n")
        code = proc.wait()
    except BaseException:          # Ctrl-C no longer reaches the builder's own group: stop it here
        watchdog.cancel()
        kill_group(proc, grace=1.0)
        raise
    watchdog.cancel()
    kill_group(proc, grace=1.0)    # nothing the builder started may keep running (and saving) after it ended
    stop.set()
    tailer.join(timeout=5)
    end = datetime.now(timezone.utc)

    trace_file, trace_text, trace_problems = (chosen[0].path, *chosen[0].finish()) if chosen else (None, "", [])
    records = []
    for line in trace_text.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            records.append({"type": "unreadable line"})
    summary = summarize_trace(records, arrivals if len(arrivals) == len(records) else None, str(ws))
    if trace_text:
        (run_dir / "trace.jsonl").write_text(redact(trace_text, secrets))

    # What the run created or updated on Freya: slots that are new or whose version moved.
    sys.path.insert(0, str(ws))
    import freya  # noqa: E402  reads FREYA_API_KEY at import, so only after os.environ is set
    state_after = json.loads((state / "freya-agents.json").read_text())
    freya_objects = []
    for slot, s in state_after.items():
        if state_before.get(slot) != s:
            path = run_dir / f"{slot}.workflow.json"
            try:
                freya.export_workflow(s["workflow_id"], str(path))
                exported = path.name
            except Exception as e:  # keep the run record even if the export fails
                exported = f"export failed: {e}"
            freya_objects.append({"slot": slot, **s, "created": slot not in state_before, "export": exported,
                                  "export_sha256": sha256(path) if path.is_file() else None})

    input_problems = input_changes(manifest, ws) + unexpected_traces(ws, trace_file) + trace_problems
    with tempfile.TemporaryDirectory() as d:
        checks = check_exports(run_dir, ws, freya_objects, contract_required=skill is not None,
                               api_data=json.loads(manifest["tools/openapi.json"]["data"]),
                               evidence_base=pristine_inputs(manifest, Path(d)),
                               evidence_texts={rel: m["data"].decode(errors="replace") for rel, m in manifest.items()})
    end_total = datetime.now(timezone.utc)

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
    seconds_total = (end_total - start).total_seconds()
    sdk_reason = sdk_outcome(final_result(records)) or console_confirms(console, trace_file, records)
    exit_status, reasons = accept(code, timed_out.is_set(), sdk_reason, seconds_total, minutes * 60, checks, input_problems)
    info = {
        "run": run_dir.name, "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
        "seconds": round((end - start).total_seconds()), "limit_minutes": minutes, "timed_out": timed_out.is_set(), "exit_code": code,
        "acceptance": {"accepted": exit_status == 0, "exit": exit_status, "reasons": reasons,
                       "sdk_result": final_result(records) or "no ResultMessage as the trace's last record",
                       "inputs_unchanged": not input_problems, "end_total": end_total.isoformat(timespec="seconds"),
                       "seconds_total": round(seconds_total)},
        "builder": "docs/build-the-builder/examples/agent_builder.py (unchanged), skill "
                   + (f"{redact(str(skill), {})} (sha256:{sha256(skill / 'SKILL.md')[:12]})" if skill else "build-phone-agent from the kit"),
        "builder_model": model or "claude-opus-5-5 (agent_builder.py default)", "agent_model": freya.AGENT_LLM,
        "repo_commit": commit, "repo_dirty": dirty, "isolation": {"CLAUDE_CONFIG_DIR": "<repo>/.claude-builder", "HOME": "<repo>/.claude-builder/home",
                                                                  "state": redact(str(state), {})},
        "inputs": {"briefs": [{"name": b.name, "sha256": sha256(b)} for b in briefs], "tools": {"name": tools.name, "sha256": sha256(tools)}},
        "practice_cases": [c["id"] for c in json.loads((ws / "public-test-set.json").read_text())],
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
        info["acceptance"].update(accepted=False, exit=2, reasons=info["acceptance"]["reasons"] + [f"secret found in {leaks}"])
        (run_dir / "summary.json").write_text(redact(json.dumps(info, indent=1, default=str), secrets))
        return 2
    return exit_status


def check_exports(run_dir: Path, ws: Path, freya_objects: list[dict], contract_required: bool = False,
                  api_path: Path | None = None, evidence_base: Path | None = None,
                  evidence_sources: set[str] | None = None, api_data: dict | None = None,
                  evidence_texts: dict[str, str] | None = None) -> list[dict]:
    """Static checks of every exported workflow against the run's tool API, with the builder's contract if it wrote one.

    Fails closed: a run that saved nothing, a missing export, and (when the skill requires one) a missing, unreadable or
    empty contract are errors, so they cannot pass as a clean check. `api_path` and `evidence_base` name the original
    inputs; without them the workspace copies are used, which the builder could have changed. With `evidence_sources`
    a contract quote may name only those input paths: an absolute path or `..` would leave `evidence_base`.
    `api_data` and `evidence_texts` (input path -> text) are the inputs as the runner read them before the build;
    with them the tool API and every quote are checked in memory, and that check decides."""
    from .workflow_check import check
    if not freya_objects:
        return [{"slot": "(none)", "contract": None, "errors": ["the run saved no workflow on Freya"], "warnings": 0}]
    api = api_data if api_data is not None else json.loads((api_path or ws / "tools" / "openapi.json").read_text())
    if evidence_texts is not None:
        evidence_sources = set(evidence_texts)
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
            if contract is not None and not isinstance(contract, dict):
                entry["errors"].append(f"{cpath.name} is not a JSON object")
                contract = None
            elif contract is not None and not (isinstance(contract.get("terminal_tools", []), list)
                                               and all(isinstance(t, dict) for t in contract.get("terminal_tools") or [])):
                entry["errors"].append(f"{cpath.name}: terminal_tools is not a list of objects")
                contract = None
            elif contract_required and contract is not None and not contract.get("terminal_tools"):
                entry["errors"].append(f"{cpath.name} declares no terminal tool, so terminal-tool ordering was not checked")
            if contract is not None and evidence_sources is not None:
                for t in contract.get("terminal_tools") or []:
                    for ev in (t.get("evidence") if isinstance(t, dict) else None) or []:
                        src = str(ev.get("source", "")) if isinstance(ev, dict) else ""
                        if src not in evidence_sources:
                            entry["errors"].append(f"{cpath.name}: evidence source {src[:80]!r} is not one of the input files {sorted(evidence_sources)}")
                        elif evidence_texts is not None:
                            quote = " ".join(str(ev.get("quote", "")).split())
                            if not quote or quote not in " ".join(evidence_texts[src].split()):
                                entry["errors"].append(f"{cpath.name}: quote not in {src} as the runner read it before the build: {quote[:80]!r}")
        elif contract_required:
            entry["errors"].append(f"{cpath.name} is missing, so terminal-tool ordering could not be checked")
        found = check(json.loads(path.read_text()), api, contract, evidence_base or ws)
        entry["errors"] += [str(x) for x in found if x.level == "error"]
        entry["warnings"] = sum(x.level == "warning" for x in found)
        entry["lowering"] = lowering_provenance(ws, f["slot"], json.loads(path.read_text()), api)
    return out


def lowering_provenance(ws: Path, slot: str, export: dict, api: dict) -> str:
    """Whether the saved workflow's endings are the ones tools/lower.py writes from the builder's body and plan."""
    from .lower import LoweringError, lower
    from .workflow_check import _all_nodes, load_operations, tool_operation
    body, plan, lowered = (ws / "out" / f"{slot}.{x}.json" for x in ("body", "closing", "workflow"))
    if not (body.is_file() and plan.is_file()):
        return "not lowered: no out/<slot>.body.json and out/<slot>.closing.json"
    try:
        again, _ = lower(json.loads(body.read_text()), json.loads(plan.read_text()), api, ws)
    except (LoweringError, ValueError, KeyError) as e:
        return f"the body and plan do not lower: {e}"
    if not lowered.is_file() or json.loads(lowered.read_text()) != again:
        return "out/<slot>.workflow.json differs from what the body and plan lower to (edited after lowering?)"
    ops, term = load_operations(api), json.loads(plan.read_text())["terminal"]["tool"]

    def endings(wf):
        nodes = _all_nodes(wf)
        steps = {k for k, n in nodes.items() if any(tool_operation(t, ops) == term for t in (n.get("tools") or []) + (n.get("pre_actions") or []))}
        sent = {k: json.dumps(nodes[k]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"], sort_keys=True)
                for k in steps if nodes[k].get("pre_actions")}
        routes = sorted((k, t.get("target_node")) for k, n in nodes.items() for t in n.get("transitions") or [] if t.get("target_node") in steps)
        return steps, sent, routes

    a, b = endings(again), endings(export.get("workflow", export))
    if a == b:
        return "matches: every ending step, value and route of the saved workflow comes from the lowering"
    return (f"saved workflow differs from the lowering: steps {sorted(a[0] ^ b[0]) or 'same'}, "
            f"values {'same' if a[1] == b[1] else 'differ'}, routes {'same' if a[2] == b[2] else 'differ'}")


def render_result(info: dict) -> str:
    tests = ", ".join(f"{t['passed']}/{t['total']}" for t in info["tests"]) or "none"
    cost = info["cost_usd"]
    return (f"{info['seconds']} s, cost {'$%.2f' % cost if cost is not None else 'unknown'}, builder tests: {tests}, "
            f"exit {info['exit_code']}{', TIMED OUT' if info['timed_out'] else ''}")


def render_trace(info: dict) -> str:
    """Plain-text trace: start and end, every model call with a one-line purpose, what was created on Freya, tests."""
    L = [f"Freya builder trace: {info['run']}",
         f"start {info['start']}  end {info['end']}  ({info['seconds']} s, limit {info['limit_minutes']:g} min{', TIMED OUT' if info['timed_out'] else ''})",
         *([f"with export and checks: end {info['acceptance']['end_total']} ({info['acceptance']['seconds_total']} s)"] if info.get("acceptance") else []),
         f"builder: {info['builder']}; model {info['builder_model']}",
         f"phone agent model: {info['agent_model']['provider']}/{info['agent_model']['model']} (set by freya.py)",
         f"repo commit {info['repo_commit']}{' (uncommitted changes)' if info['repo_dirty'] else ''}",
         "inputs: " + ", ".join(f"{b['name']} sha256:{b['sha256'][:12]}" for b in info["inputs"]["briefs"]) + f"; tools {info['inputs']['tools']['name']} sha256:{info['inputs']['tools']['sha256'][:12]}",
         "practice customers in the workspace: " + (", ".join(info.get("practice_cases") or []) or "none (no kit brief matches the input)"),
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
        if c.get("lowering"):
            L.append(f"     endings: {c['lowering']}")
    L += ["", f"files the builder wrote: {', '.join(info['written']) or 'none'}", f"result: {render_result(info)}"]
    if info.get("acceptance"):
        a = info["acceptance"]
        L.append(f"acceptance: {'ACCEPTED' if a['accepted'] else 'NOT ACCEPTED'} (exit {a['exit']}), SDK result {a['sdk_result']}, "
                 f"inputs {'unchanged' if a['inputs_unchanged'] else 'CHANGED'}")
        L += [f"  - {r}" for r in a["reasons"]]
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m builder.kitrun", description=__doc__.split("\n\n")[0])
    p.add_argument("briefs", nargs="+", type=Path)
    p.add_argument("--tools", type=Path, required=True, help="the brief's tool API file (OpenAPI JSON)")
    p.add_argument("--label", default="kit", help="suffix of the run directory name")
    p.add_argument("--model", help="builder model (BUILDER_MODEL); default: agent_builder.py's own default")
    p.add_argument("--minutes", type=float, default=30, help="hard time limit for the whole build (default 30)")
    p.add_argument("--skill", type=Path, help="skill directory that replaces the kit's build-phone-agent skill in the workspace")
    p.add_argument("--state", type=Path, default=STATE, help="directory for this run's slot and persona ids (default state/, shared)")
    a = p.parse_args(argv)
    for f in [*a.briefs, a.tools]:
        if not f.is_file():
            p.error(f"no such file: {f}")
    if a.skill and not (a.skill / "SKILL.md").is_file():
        p.error(f"no SKILL.md in {a.skill}")
    return run([b.resolve() for b in a.briefs], a.tools.resolve(), a.label, a.model, a.minutes, a.skill.resolve() if a.skill else None,
               a.state.resolve())


if __name__ == "__main__":
    sys.exit(main())
