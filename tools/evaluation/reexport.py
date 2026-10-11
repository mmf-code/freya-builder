"""Re-export a kitrun run's workflows (read-only GET) and run kitrun's own post-build checks on them.

    python3 -I tools/evaluation/reexport.py REPO RUN_DIR STATE_DIR

The checks use the run's input files only after their workspace copies match the sha256 that summary.json recorded,
and contract quotes may name only those inputs, as in kitrun. Prints each export's sha256. Exit 3 on any error."""
import hashlib
import json
import os
import sys
from pathlib import Path

repo, run_dir, state = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
sys.path.insert(0, str(repo))
from builder.kitrun import check_exports, load_env  # noqa: E402

os.environ.update(load_env(repo / "docs/build-the-builder/env.sh"))
sys.path.insert(0, str(repo / "docs/build-the-builder"))
import freya  # noqa: E402

ws = run_dir / "workspace"
inputs = json.loads((run_dir / "summary.json").read_text())["inputs"]
recorded = {f"briefs/{b['name']}": b["sha256"] for b in inputs["briefs"]} | {"tools/openapi.json": inputs["tools"]["sha256"]}
bad = [rel for rel, h in recorded.items() if not (ws / rel).is_file() or hashlib.sha256((ws / rel).read_bytes()).hexdigest() != h]
for rel in bad:
    print("input", rel, "differs from the sha256 in summary.json; its quotes can not be checked")

objects = []
for slot, s in json.loads((state / "freya-agents.json").read_text()).items():
    path = run_dir / f"{slot}.workflow.json"
    freya.export_workflow(s["workflow_id"], str(path))
    exported = json.loads(path.read_text())
    print(slot, "exported", s["workflow_id"][:8], "updated_at", exported.get("updated_at"), "state version", s.get("version"),
          "sha256", hashlib.sha256(path.read_bytes()).hexdigest()[:12])
    objects.append({"slot": slot, **s})
errors = bool(bad)
for c in check_exports(run_dir, ws, objects, contract_required=True, evidence_sources=set(recorded)):
    errors = errors or bool(c["errors"])
    print(c["slot"], "errors", c["errors"], "warnings", c["warnings"], "contract", c["contract"], "|", c.get("lowering"))
sys.exit(3 if errors else 0)
