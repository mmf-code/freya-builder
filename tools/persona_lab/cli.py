"""Persona Lab command line. Run from the repository root.

    python3 -m tools.persona_lab.cli generate                 # personas + blind scenarios, deterministic
    python3 -m tools.persona_lab.cli list
    python3 -m tools.persona_lab.cli grade EXPORT.json SCENARIO   # SCENARIO: e.g. g6-contract-clean, or a directory
    python3 -m tools.persona_lab.cli grade-runs                  # every blind build found under runs/*-pl-*
    python3 -m tools.persona_lab.cli run --agent-a ID --agent-b ID [--select shortlist|all|V09,V06] [--reps 1] [--live]
    python3 -m tools.persona_lab.cli report RESULTS_DIR

Only `run --live` touches the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import blind, grade, personas, runner
from .common import GEN


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 -m tools.persona_lab.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("generate")
    sub.add_parser("list")
    g = sub.add_parser("grade")
    g.add_argument("export", type=Path)
    g.add_argument("scenario")
    g.add_argument("--json", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--agent-a")
    r.add_argument("--agent-b")
    r.add_argument("--workflow-a", help="workflow id of the A agent, exported into the results for traceability")
    r.add_argument("--workflow-b")
    r.add_argument("--select", default="shortlist")
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--live", action="store_true")
    r.add_argument("--out", type=Path)
    sub.add_parser("grade-runs", help="grade every fresh blind-build export found on disk")
    rp = sub.add_parser("report")
    rp.add_argument("dir", type=Path)
    a = p.parse_args(argv)

    if a.cmd == "generate":
        res = personas.compile_all()
        if res["problems"]:
            for v, errs in res["problems"].items():
                for e in errs:
                    print(f"INVALID {v}: {e}")
            return 1
        idx = blind.build()
        print(f"{res['compiled']} persona variants -> {GEN / 'personas'}")
        print(f"{len(idx)} blind scenario inputs -> {GEN / 'blind'}")
        return 0
    if a.cmd == "list":
        manifest, _, _ = runner.load_compiled()
        for v, m in sorted(manifest.items(), key=lambda x: x[1]["rank"]):
            star = "*" if v in runner.SHORTLIST else " "
            print(f"{star} {v} rank {m['rank']:>2} {m['base_case']} brief {m['brief']} {m['layer']:<10} {','.join(m['families'])}")
        for s in json.loads((GEN / "blind" / "index.json").read_text()):
            print(f"  {s['dir']:<22} {s['family']}")
        return 0
    if a.cmd == "grade":
        d = Path(a.scenario) if Path(a.scenario).is_dir() else GEN / "blind" / a.scenario
        res = grade.grade_paths(a.export, d)
        print(json.dumps(res, indent=1) if a.json else grade.render(res))
        return 0 if res["contract"]["pass"] and not res["strong_stale"] else 1
    if a.cmd == "grade-runs":
        found, bad = grade.fresh_exports(), 0
        for export, scn in found:
            res = grade.grade_paths(export, scn)
            bad += not res["contract"]["pass"] or bool(res["strong_stale"])
            print(f"{export}\n{grade.render(res)}\n")
        print(f"{len(found)} fresh exports graded, {bad} with a contract failure or strong stale evidence")
        return 1 if bad else 0
    if a.cmd == "run":
        manifest, _, _ = runner.load_compiled()
        chosen = runner.select(manifest, a.select)
        runner.run(chosen, {"A": a.agent_a, "B": a.agent_b}, a.reps, a.live, {"A": a.workflow_a, "B": a.workflow_b}, a.out)
        return 0
    if a.cmd == "report":
        print(runner.render_report(runner.report(a.dir)))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
