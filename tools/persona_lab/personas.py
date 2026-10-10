"""Compile behaviour specs into kit-compatible cases and Freya persona prompts, and refuse unfair ones.

A compiled case is the base public case, unchanged, plus `style: "pl-<variant>"`. The behaviour block is registered
as that kit style, so the kit's own `persona_for` appends it after the kit RULES exactly like `--style talkative`.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from . import acts as A
from .common import COMPILER_VERSION, GEN, LAB, canon, kit_path, load_cases, sha256, write_json

FROZEN = ("id", "brief", "family", "level", "title", "script", "variables", "identity", "products", "expected", "checks", "faults", "third_party")
TRUTH_NUM = re.compile(r"\d+(?:\.\d+)?")


def load_specs() -> list[dict]:
    return json.loads((LAB / "variants.json").read_text())


def frozen_part(case: dict) -> dict:
    return {k: case.get(k) for k in FROZEN}


# ---------------------------------------------------------------- lint (EVRE protocol checks, reduced)

def lint(spec: dict) -> list[str]:
    errs = []
    ids = [a["id"] for a in spec["acts"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate act ids")
    conds = set(spec.get("conditions", {}))
    for a in spec["acts"]:
        if a["use"] not in A.ACTS:
            errs.append(f"{a['id']}: unknown act type {a['use']}")
        if a.get("max", 1) < 1:
            errs.append(f"{a['id']}: max must be at least 1")
    reach = set()
    for kind in ("rules", "escalation"):
        for r in spec.get(kind, []):
            for c in r["when"]:
                if c not in conds:
                    errs.append(f"{kind}: unknown condition {c}")
            for a in r["acts"]:
                if a not in ids:
                    errs.append(f"{kind}: unknown act {a}")
                reach.add(a)
    for a in ids:
        if a not in reach:
            errs.append(f"{a}: no rule or escalation selects it")
    graph = {}
    for o in spec.get("ordering", []):
        for x in (o["before"], o["after"]):
            if x not in ids:
                errs.append(f"ordering: unknown act {x}")
        graph.setdefault(o["before"], set()).add(o["after"])

    def cyclic(n, seen):
        return any(m in seen or cyclic(m, seen | {m}) for m in graph.get(n, ()))
    if any(cyclic(n, {n}) for n in graph):
        errs.append("ordering has a cycle")
    for k in ("hypothesis", "proves", "does_not_prove", "expected_agent"):
        if not spec.get(k):
            errs.append(f"missing {k}")
    return errs


# ---------------------------------------------------------------- consistency with the base case

def _truth_numbers(case: dict) -> set[str]:
    blob = json.dumps({k: case[k] for k in ("identity", "products", "expected", "variables", "script")})
    nums = set(TRUTH_NUM.findall(blob))
    nums |= {n.rstrip("0").rstrip(".") for n in nums if "." in n}
    return nums


def _identity_digits(case: dict) -> list[str]:
    return [re.sub(r"\D", "", str(v)) for v in case["identity"].values()]


def consistency(spec: dict, case: dict, behaviour: str) -> list[str]:
    errs = []
    truth = _truth_numbers(case)
    distract = {d["value"] for d in spec.get("distractors", [])}
    for d in distract & truth:
        errs.append(f"distractor {d} equals a fact of {case['id']}")
    for n in TRUTH_NUM.findall(behaviour):
        if n in truth or n in distract:
            continue
        if len(n) >= 2 and any(n in digits for digits in _identity_digits(case)):
            continue                                 # a fragment of a split security answer
        errs.append(f"number {n} is neither a fact of {case['id']} nor a declared distractor")
    corrects_in_base = bool(re.search(r"\bthen\b", case["script"])) and case["family"] in ("Identity", "Multi-product")
    for a in spec["acts"]:
        if a["use"] == "self_correct" and re.search(r"birth|phone|digit|security|postcode", json.dumps(a["args"]), re.I) and not corrects_in_base:
            errs.append(f"{a['id']}: corrects a security answer the base case gives right the first time")
    if spec["layer"] == "official" and spec.get("rules") and not spec.get("expected_agent"):
        errs.append("official variant without expected agent behaviour")
    return errs


# ---------------------------------------------------------------- compile

def behaviour_block(spec: dict) -> str:
    acts = {a["id"]: a for a in spec["acts"]}
    cond = spec.get("conditions", {})
    tag = {aid: f"B{i}" for i, aid in enumerate(acts, 1)}
    lines = ["HOW YOU BEHAVE IN THIS CALL. Keep track of what you have already done; each behaviour has a limit and "
             "once it is used up you never do it again. These behaviours change only how you talk. What you finally "
             "agree to, refuse or answer stays exactly as written above."]
    for r in sorted(spec.get("rules", []), key=lambda r: -r.get("priority", 0)):
        when = " and ".join(cond[c] for c in r["when"])
        for aid in r["acts"]:
            lines.append(f"- {tag[aid]}. When {when}: {A.render(acts[aid])}")
    for r in spec.get("escalation", []):
        when = " and ".join(cond[c] for c in r["when"])
        for aid in r["acts"]:
            lines.append(f"- {tag[aid]}. If {when}: {A.render(acts[aid])}")
    for o in spec.get("ordering", []):
        lines.append(f"- Do {tag[o['after']]} only after you have done {tag[o['before']]}.")
    return "\n".join(lines)


def compile_spec(spec: dict, cases: dict[str, dict]) -> tuple[dict, dict, list[str]]:
    base = cases[spec["base_case"]]
    block = behaviour_block(spec)
    errs = lint(spec) + consistency(spec, base, "\n".join(A.render(a) for a in spec["acts"]))
    case = copy.deepcopy(base)
    case["style"] = "pl-" + spec["id"]
    if frozen_part(case) != frozen_part(base):
        errs.append("compiled case changed a frozen field")
    kit_path()
    import run_cases                                      # kit module; no network on import
    run_cases.STYLES[case["style"]] = block                # appended after the kit RULES, like the kit's own styles
    persona = run_cases.persona_for(case, {"identity": case["identity"]})
    key = case["id"] + ":" + hashlib.sha1(json.dumps(persona, sort_keys=True).encode()).hexdigest()[:10]
    meta = {"variant": spec["id"], "layer": spec["layer"], "rank": spec["rank"], "seed": spec["seed"],
            "base_case": base["id"], "brief": base["brief"], "families": spec["families"],
            "spec_hash": sha256(spec), "base_frozen_hash": sha256(frozen_part(base)),
            "compiler_version": COMPILER_VERSION, "persona_key": key, "persona_hash": sha256(persona),
            "ledger_scored": spec["layer"] == "official"}
    return case, {"persona": persona, "meta": meta}, errs


def compile_all(out=GEN / "personas") -> dict:
    cases = load_cases()
    manifest, compiled, problems, personas_out = {}, [], {}, {}
    for spec in load_specs():
        case, rendered, errs = compile_spec(spec, cases)
        if errs:
            problems[spec["id"]] = errs
            continue
        compiled.append(case)
        manifest[spec["id"]] = rendered["meta"]
        (out / "prompts").mkdir(parents=True, exist_ok=True)
        (out / "prompts" / f"{spec['id']}.txt").write_text(rendered["persona"]["prompt"] + "\n")
        personas_out[spec["id"]] = rendered["persona"]
    if not problems:
        write_json(out / "cases.json", compiled)
        write_json(out / "personas.json", personas_out)       # the exact persona objects the runner uploads
        write_json(out / "manifest.json", {"compiler_version": COMPILER_VERSION, "variants": manifest,
                                           "suite_hash": sha256(canon(manifest))})
    return {"compiled": len(compiled), "problems": problems}
