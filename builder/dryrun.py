"""Run a workflow's code steps locally on sample variables and show what each one writes. Standard library only.

    python3 tools/dryrun.py WORKFLOW.json SAMPLES.json [--steps a,b]

SAMPLES.json is a list of samples, each a dict of variables as the engine would hold them when the code runs: call
variables (for example `now`) and tool results (for example `<step>_response.data`). Each code step runs as the
engine runs a code_exec step, on one shared `vars` dict, in the order of --steps or of the workflow file. For every
sample the tool prints each variable a step wrote or changed, and any exception (the engine would record it as a
failed step and keep the old values). Use it before saving: several `now` dates (a Friday, a weekend day, the day
before a holiday), and each kind of tool result the brief names. It shows what the code computes, not what the model
says. Exit status: 0 every step ran on every sample, 1 a step raised, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


def code_steps(wf: dict) -> list[tuple[str, str]]:
    out = []
    for key, node in (wf.get("nodes") or {}).items():
        for t in node.get("pre_actions") or []:
            fn = (t or {}).get("function") or {}
            if fn.get("handler") == "__function__:code_exec":
                out.append((key, str(((fn.get("parameters") or {}).get("properties") or {}).get("code", {}).get("default") or "")))
    return out


def run_step(code: str, variables: dict) -> str | None:
    env = {"vars": variables, "_json": json, "_result": None}
    try:
        exec(compile(code, "<code step>", "exec"), env, env)
    except Exception as e:  # reported, as the engine would record a failed step
        return f"{type(e).__name__}: {e}"
    return None


def dry_run(wf: dict, sample: dict, only: list[str] | None = None) -> list[dict]:
    steps = code_steps(wf)
    if only:
        by_key = dict(steps)
        steps = [(k, by_key[k]) for k in only if k in by_key]
    variables, report = copy.deepcopy(sample), []
    for key, code in steps:
        before = copy.deepcopy(variables)
        error = run_step(code, variables)
        written = {k: v for k, v in variables.items() if k not in before or before[k] != v}
        report.append({"step": key, "error": error, "written": written})
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("workflow", type=Path)
    p.add_argument("samples", type=Path)
    p.add_argument("--steps", help="comma-separated code steps to run, in this order")
    a = p.parse_args(argv)
    try:
        wf, samples = json.loads(a.workflow.read_text()), json.loads(a.samples.read_text())
    except (OSError, ValueError) as e:
        print(f"cannot read input: {e}", file=sys.stderr)
        return 2
    wf = wf["workflow"] if "nodes" not in wf and isinstance(wf.get("workflow"), dict) else wf
    failed = False
    for i, sample in enumerate(samples if isinstance(samples, list) else [samples], 1):
        print(f"== sample {i}: " + ", ".join(f"{k}={v}" for k, v in sample.items() if isinstance(v, (str, int, float)))[:200])
        for r in dry_run(wf, sample, a.steps.split(",") if a.steps else None):
            if r["error"]:
                failed = True
                print(f"  {r['step']}: RAISED {r['error']}")
            for k, v in r["written"].items():
                text = v if isinstance(v, str) else json.dumps(v)
                print(f"  {r['step']} -> {k} = {text[:600]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
