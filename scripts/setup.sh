#!/usr/bin/env bash
# Create .venv with the builder's dependencies. Safe to re-run. Use it as the cloud environment's setup script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -x "$ROOT/.venv/bin/python" ] || python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --quiet claude-agent-sdk==0.2.165
