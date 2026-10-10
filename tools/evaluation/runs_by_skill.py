"""Which skill made which run: the skill sha256 from each run's summary.json, named after builder/skills/.

    python3 -I tools/evaluation/runs_by_skill.py REPO [GLOB]      # GLOB default: runs/*"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
pattern = sys.argv[2] if len(sys.argv) > 2 else "runs/*"
names = {hashlib.sha256((d / "SKILL.md").read_bytes()).hexdigest()[:12]: d.name
         for d in sorted((repo / "builder/skills").iterdir()) if (d / "SKILL.md").is_file()}
for run in sorted(repo.glob(pattern)):
    f = run / "summary.json"
    if not f.is_file():
        continue
    s = json.loads(f.read_text())
    b = s.get("builder", "")
    sha = b.split("sha256:")[1][:12] if "sha256:" in b else "kit"
    print(f"{run.name:40} {sha:13} {names.get(sha, '(kit skill)' if sha == 'kit' else '?'):20} {s.get('seconds')} s"
          f"{' TIMED OUT' if s.get('timed_out') else ''}  state={s.get('isolation', {}).get('state', 'state/ (shared)')}"
          f"  slots={[x['slot'] for x in s.get('freya') or []]}")
