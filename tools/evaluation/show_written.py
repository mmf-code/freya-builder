"""Print what a workflow's code steps write for one sample product and `now`, filtered by a word.

    python3 tools/evaluation/show_written.py RUN_DIR WORD [DAYS_LATE] [TYPE] [PAST_DUE] [NOW]

The product is fed under every name the engine could give the get_account result (see pl_semantic.py)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from builder.dryrun import dry_run  # noqa: E402

run, word = Path(sys.argv[1]), sys.argv[2].lower()
days_late = int(sys.argv[3]) if len(sys.argv) > 3 else 16
ptype = sys.argv[4] if len(sys.argv) > 4 else "car_loan"
past_due = float(sys.argv[5]) if len(sys.argv) > 5 else 2500.0
now = sys.argv[6] if len(sys.argv) > 6 else "2026-10-14T11:00"
wf = json.loads(next(run.glob("*.workflow.json")).read_text())
wf = wf.get("workflow", wf)
product = {"product_id": "p1", "type": ptype, "past_due": past_due, "days_late": days_late, "instalment_amount": 300.0, "minimum_payment": 60.0}
data = {"ok": True, "products": [product]}
sample = {"now": now, "customer_id": "c_test", "title": "Mr", "first_name": "Ann", "last_name": "Lee"}
for k, n in wf["nodes"].items():
    for t in (n.get("pre_actions") or []) + (n.get("tools") or []):
        if isinstance(t, dict) and "get_account" in json.dumps(t.get("function", {}).get("parameters", {}))[:400]:
            for name in (f"{k}_response", f"{t['function']['name']}_response"):
                sample.update({name: {"data": data}, f"{name}.data": data, f"{name}.data.products": [product], f"{name}.data.ok": True})
for r in dry_run(wf, sample):
    for key, value in r["written"].items():
        text = value if isinstance(value, str) else json.dumps(value)
        if word in key.lower() or word in text.lower():
            hits = [m.start() for m in re.finditer(re.escape(word), text.lower())] or [0]
            print(f"{r['step']} -> {key} = " + " | ".join(text[max(0, h - 80):h + 120].replace(chr(10), " ") for h in hits[:3]))
    if r["error"]:
        print(f"{r['step']} RAISED {r['error']}")
