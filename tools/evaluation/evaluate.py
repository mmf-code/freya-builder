"""Run the official practice cases for one agent from a kitrun workspace. Raw output is kept as run_cases writes it.

    python evaluate.py REPO RUN_DIR AGENT_ID BRIEF_LETTER NAME [--reps N]

The kit env is read from REPO/docs/build-the-builder/env.sh with kitrun.load_env and passed to the child process;
nothing is printed from it."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("repo", type=Path)
p.add_argument("run_dir", type=Path)
p.add_argument("agent")
p.add_argument("brief")
p.add_argument("name")
p.add_argument("--reps", type=int, default=1)
p.add_argument("--cases", type=Path, help="case file; default: the workspace's own (empty for a hidden brief)")
a = p.parse_args()
sys.path.insert(0, str(a.repo))
from builder.kitrun import load_env, secrets_of, redact  # noqa: E402

env_file = a.repo / "docs/build-the-builder/env.sh"
env = load_env(env_file)
secrets = secrets_of(env)
out = a.run_dir.resolve() / "eval"
out.mkdir(exist_ok=True)
cmd = ["python3", "-u", "tools/run_cases.py", a.agent, "--brief", a.brief, "--out", str(out / f"{a.name}.json")]
if a.reps > 1:
    cmd += ["--reps", str(a.reps)]
if a.cases:
    cmd += ["--cases", str(a.cases.resolve())]
with open(out / f"{a.name}.log", "w") as log:
    proc = subprocess.Popen(cmd, cwd=a.run_dir / "workspace", env={**os.environ, **env}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        line = redact(line, secrets)
        log.write(line)
        log.flush()
        print(line, end="", flush=True)
sys.exit(proc.wait())
