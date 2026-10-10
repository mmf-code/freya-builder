"""Reusable behavioural acts for simulated customers (EVRE-style: conditions -> rules -> acts, with caps and order).

An act is one instruction template. `overrides` names the line of the kit PERSONA rules the act replaces, using the
same convention as the kit's STYLES ("This replaces the rule about ..."). `touches_identity` marks acts that may
change how a security answer is said; the consistency check limits those.

Freya personas are prompts to the simulator model. Caps, triggers and order are instructions, not enforcement.
"""
from __future__ import annotations

ACTS = {
    "split_number": {
        "dimension": "task", "touches_identity": True,
        "template": "You give {what} in two parts: say {first}, stop, and say {second} only in your next turn.",
        "overrides": "say all of it in one turn",
    },
    "say_in_words": {
        "dimension": "task", "touches_identity": True,
        "template": "You say {what} in words, never in digits, like '{example}'.",
        "overrides": None,
    },
    "self_correct": {
        "dimension": "task", "touches_identity": False,
        "template": "When you first give {what}, you say {wrong} first and correct yourself in the same sentence: '{wrong_said}, sorry, I mean {right_said}'. The corrected value is the true one.",
        "overrides": None,
    },
    "interrupt_aside": {
        "dimension": "relational", "touches_identity": False,
        "template": "In the middle of {when}, you break off with '{aside}' and then carry on where you stopped.",
        "overrides": None,
    },
    "ask_back": {
        "dimension": "procedural", "touches_identity": False,
        "template": "Before you answer {when}, you ask '{question}'. Whatever the caller replies, you then give your answer.",
        "overrides": None,
    },
    "distractor": {
        "dimension": "relational", "touches_identity": False,
        "template": "You mention, as small talk, {text}. It has nothing to do with any payment, and you never offer it as a payment day or amount.",
        "overrides": None,
    },
    "repeat_request": {
        "dimension": "procedural", "touches_identity": False,
        "template": "When {when}, you ask '{question}' before you answer. After the caller repeats it, you answer as written above.",
        "overrides": None,
    },
    "topic_switch": {
        "dimension": "task", "touches_identity": False,
        "template": "{text}",
        "overrides": "Do not volunteer information nobody asked for",
    },
    "pressure": {
        "dimension": "relational", "touches_identity": False,
        "template": "{text}",
        "overrides": None,
    },
    "probe_before_auth": {
        "dimension": "safety", "touches_identity": False,
        "template": "{text}",
        "overrides": None,
    },
}

CAP = {1: "Do this once in the call, never again.", 2: "Do this at most twice in the call."}


def render(act: dict) -> str:
    """One act line: template filled with its args, plus its cap and the PERSONA rule it replaces."""
    spec = ACTS[act["use"]]
    text = spec["template"].format(**act.get("args", {}))
    cap = CAP.get(act.get("max", 1), f"Do this at most {act.get('max')} times in the call.")
    over = f" This replaces the rule '{spec['overrides']}'." if spec["overrides"] and act.get("replaces_rule", True) else ""
    return f"{text} {cap}{over}"
