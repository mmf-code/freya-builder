"""Re-export a kitrun run's workflows (read-only GET) and run kitrun's own post-build checks on them.

    python export_retry.py REPO RUN_DIR STATE_DIR"""
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

objects = []
for slot, s in json.loads((state / "freya-agents.json").read_text()).items():
    path = run_dir / f"{slot}.workflow.json"
    freya.export_workflow(s["workflow_id"], str(path))
    exported = json.loads(path.read_text())
    print(slot, "exported", s["workflow_id"][:8], "updated_at", exported.get("updated_at"), "state version", s.get("version"))
    objects.append({"slot": slot, **s})
for c in check_exports(run_dir, run_dir / "workspace", objects, contract_required=True):
    print(c["slot"], "errors", c["errors"], "warnings", c["warnings"], "contract", c["contract"], "|", c.get("lowering"))
