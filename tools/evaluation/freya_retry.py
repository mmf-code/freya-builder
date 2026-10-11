"""Retry the kit client's API calls on platform errors, for our evaluation tools only (never inside a build).

    from tools.evaluation.freya_retry import install; install(freya)
    python3 -u tools/evaluation/freya_retry.py SCRIPT ARGS...   # run a kit script (run_cases.py) with retries installed

The kit's freya.api raises on the first 5xx and has a 120 s timeout. During the outages of 2026-10-10 and -11 that
ended evaluation runs whose simulations went on running on Freya. GET requests are retried on 5xx and timeouts. A
POST that creates a simulation is, after a 5xx or a timeout, first looked up by its name and agent: if the platform
created it anyway, that simulation is used; if not, the POST is sent again. Any other POST or PUT is retried only on
"API key validation is temporarily unavailable" (503), which the platform answers before it does anything.
"""
from __future__ import annotations

import runpy
import sys
import time

WAITS = (10, 20, 30, 45, 60, 90, 120, 180, 240)   # about 13 minutes in all: outages on 2026-10-11 lasted longer than 4


def _retryable(method: str, err: Exception) -> bool:
    text = str(err)
    if "API key validation is temporarily unavailable" in text:
        return True
    if method.upper() != "GET":
        return False
    return isinstance(err, (TimeoutError, OSError)) or any(f"-> {c}" in text for c in ("500", "502", "503", "504"))


def _created_anyway(plain, body) -> dict | None:
    """After a failed POST of a simulation: the simulation with this name, if the platform created it after all."""
    name = (body or {}).get("name")
    if not name:
        return None
    try:
        listed = plain("GET", "/api/v2/simulations?limit=5")
    except (RuntimeError, TimeoutError, OSError):
        return None
    for sim in (listed.get("simulations") or []) if isinstance(listed, dict) else []:
        if sim.get("name") == name and sim.get("agentId") == (body or {}).get("agentId"):
            return {"simulation": sim}
    return None


def install(freya) -> None:
    if getattr(freya.api, "_retrying", False):
        return
    plain = freya.api

    def api(method, path, body=None, **params):
        for wait in (*WAITS, None):
            try:
                return plain(method, path, body, **params)
            except (RuntimeError, TimeoutError, OSError) as e:
                if method.upper() == "POST" and path.rstrip("/") == "/api/v2/simulations" and wait is not None \
                        and (isinstance(e, (TimeoutError, OSError)) or any(f"-> {c}" in str(e) for c in ("500", "502", "503", "504"))):
                    time.sleep(wait)
                    found = _created_anyway(plain, body)     # a gateway error can hide a simulation that started
                    if found:
                        print(f"freya_retry: POST {path} failed but created {found['simulation'].get('id')}; using it", file=sys.stderr, flush=True)
                        return found
                    print(f"freya_retry: POST {path} failed ({str(e)[:80]}) and created nothing; retrying", file=sys.stderr, flush=True)
                    continue
                if wait is None or not _retryable(method, e):
                    raise
                print(f"freya_retry: {method} {path.split('?')[0]} failed ({str(e)[:80]}); retrying in {wait} s", file=sys.stderr, flush=True)
                time.sleep(wait)

    api._retrying = True
    freya.api = api


if __name__ == "__main__":
    sys.path.insert(0, ".")
    import freya

    install(freya)
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    runpy.run_path(script, run_name="__main__")
