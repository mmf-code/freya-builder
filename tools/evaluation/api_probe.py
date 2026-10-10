"""Read-only probe of the Freya API: status of the workspaces route, nothing printed from the env."""
import os
import sys
import time
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
from builder.kitrun import load_env  # noqa: E402

os.environ.update(load_env(repo / "docs/build-the-builder/env.sh"))
sys.path.insert(0, str(repo / "docs/build-the-builder"))
import freya  # noqa: E402

t0 = time.time()
try:
    r = freya.api("GET", "/api/v2/workspaces")
    print("OK", f"{time.time() - t0:.1f}s", "workspaces:", len(r.get("workspaces") or r.get("items") or r))
except Exception as e:
    print("FAIL", f"{time.time() - t0:.1f}s", str(e)[:200])
