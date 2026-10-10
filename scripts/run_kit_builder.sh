#!/usr/bin/env bash
# Run the kit's example builder (examples/agent_builder.py) with an isolated Claude Code config.
#
# Without this, the SDK's Claude Code process inherits the caller's CLAUDE_CONFIG_DIR and loads
# that user's auto-memory and personal mods (hooks) into the build. That makes builds depend on the
# machine and puts personal context into the submitted trace.
#
#   scripts/run_kit_builder.sh briefs/brief-a.md [briefs/brief-b.md]
#   BUILDER_MODEL=claude-sonnet-5-5 scripts/run_kit_builder.sh briefs/brief-a.md
#
# Needs docs/build-the-builder/env.sh with FREYA_API_KEY, FREYA_BANK_TEAM_KEY and ANTHROPIC_API_KEY.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KIT="$ROOT/docs/build-the-builder"
source "$KIT/env.sh"
: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set: the isolated config has no Claude login}"
export CLAUDE_CONFIG_DIR="$ROOT/.claude-builder"   # empty, git-ignored, owned by the builder only
# Personal mods load from ~/.claude/mods whatever CLAUDE_CONFIG_DIR says, so HOME is isolated too.
export HOME="$CLAUDE_CONFIG_DIR/home"
mkdir -p "$HOME"
cd "$KIT"
exec "$ROOT/.venv/bin/python" -u examples/agent_builder.py "$@"
