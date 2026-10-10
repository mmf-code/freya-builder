"""Paths, hashing and read-only access to the vendored kit."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
ROOT = LAB.parent.parent
KIT = ROOT / "docs" / "build-the-builder"
GEN = LAB / "generated"
RESULTS = LAB / "results"
STATE = ROOT / "state" / "persona_lab"
COMPILER_VERSION = "persona-lab-1"


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sha256(obj) -> str:
    return hashlib.sha256(obj if isinstance(obj, bytes) else canon(obj)).hexdigest()


def kit_path() -> None:
    """Make the kit's freya.py, score.py and run_cases.py importable. Appended, so they never shadow our modules.
    None of them calls the network on import."""
    for p in (str(KIT), str(KIT / "tools")):
        if p not in sys.path:
            sys.path.append(p)


def load_cases() -> dict[str, dict]:
    return {c["id"]: c for c in json.loads((KIT / "public-test-set.json").read_text())}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
