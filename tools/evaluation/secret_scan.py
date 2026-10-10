"""Check that no secret value from env.sh occurs in the given files. Prints only file names and secret names."""
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
from builder.kitrun import load_env, secrets_of  # noqa: E402

secrets = secrets_of(load_env(repo / "docs/build-the-builder/env.sh"))
hits = 0
for name in sys.stdin.read().split():
    p = repo / name
    if p.is_file():
        data = p.read_bytes()
        for k, v in secrets.items():
            if v.encode() in data:
                hits += 1
                print("SECRET", k, "in", name)
print(f"checked against {len(secrets)} secret values, {hits} hits")
