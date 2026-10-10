"""English cue lexicon for the heuristic extractor.

Plain data, kept apart from extract.py. A brief in another language gets its
own Lexicon instance; the extractor code does not change. This module must
stay free of domain vocabulary (see tests/test_invariants.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_I = re.IGNORECASE


@dataclass(frozen=True)
class Cue:
    pattern: re.Pattern[str]
    modality: str
    # The grammatical subject is the action: "Sharing scores is not allowed."
    passive: bool = False


@dataclass(frozen=True)
class Lexicon:
    name: str
    cues: tuple[Cue, ...]
    connectives: re.Pattern[str]  # condition openers: if, when, before, ...
    imperative_verbs: frozenset[str]
    reporting_verbs: frozenset[str]  # "tell ... when", "ask ... if": the connective opens an object clause
    auxiliaries: frozenset[str]
    object_starters: frozenset[str]  # words that can follow an imperative verb directly
    fillers: frozenset[str]  # stripped from the start of an action
    number_words: dict[str, int]
    count_rewrites: tuple[tuple[re.Pattern[str], str], ...]
    counter: re.Pattern[str]
    max_marker: re.Pattern[str]
    terminations: tuple[tuple[re.Pattern[str], str], ...]
    key_hints: tuple[tuple[re.Pattern[str], str], ...]  # JSON key text -> modality
    counter_keys: re.Pattern[str]
    limit_keys: re.Pattern[str]

    def to_int(self, token: str) -> int | None:
        t = token.lower()
        return int(t) if t.isdigit() else self.number_words.get(t)

    def rewrite_counts(self, text: str) -> str:
        for pattern, repl in self.count_rewrites:
            text = pattern.sub(repl, text)
        return text


def _cue(pattern: str, modality: str, passive: bool = False) -> Cue:
    return Cue(re.compile(pattern, _I), modality, passive)


_NEG_STATE = r"(?:strictly\s+)?(?:not\s+allowed|not\s+permitted|prohibited|forbidden)"
_NUM = r"(?P<n>\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_UNITS = (
    r"(?:attempts?|tries|retries|times|calls?|questions?|reminders?|requests?|offers?|prompts?|"
    r"re-?prompts?|transfers?|messages?|rounds?|warnings?|callbacks?|follow-ups?)"
)

EN = Lexicon(
    name="en",
    cues=(
        _cue(r"\b(?:must|shall)\s+(?:not|never)\b|\bmustn['’]t\b|\bshan['’]t\b", "must_not"),
        _cue(r"\bmay\s+not\b|\bcannot\b|\bcan\s+not\b|\bcan['’]t\b", "must_not"),
        _cue(r"\bnever\b", "must_not"),
        _cue(r"\bdo\s+not\b|\bdon['’]t\b", "must_not"),
        _cue(rf"\b(?:is|are)\s+{_NEG_STATE}\s+(?:to|from)\b", "must_not"),
        _cue(rf"\b(?:is|are)\s+{_NEG_STATE}\b(?!\s+(?:to|from)\b)", "must_not", passive=True),
        _cue(r"\bshould\s+(?:not|never)\b|\bshouldn['’]t\b|\bavoid\b", "should_not"),
        _cue(
            r"\b(?:must|shall)\b(?!\s+(?:not|never)\b)|\b(?:is|are)\s+required\s+to\b"
            r"|\b(?:has|have|needs?)\s+to\b|\balways\b",
            "must",
        ),
        _cue(r"\b(?:is|are)\s+(?:required|mandatory)\b(?!\s+to\b)", "must", passive=True),
        _cue(r"\bshould\b(?!\s+(?:not|never)\b)|\bought\s+to\b", "should"),
        _cue(r"\bmay\b(?!\s+(?:not|be|have)\b)|\b(?:is|are)\s+(?:allowed|permitted|free)\s+to\b", "may"),
        _cue(r"\b(?:is|are)\s+(?:allowed|permitted|acceptable)\b(?!\s+to\b)", "may", passive=True),
    ),
    connectives=re.compile(
        r"\b(?:only\s+(?:if|when|after|once|before)|as\s+soon\s+as|as\s+long\s+as|provided\s+that|in\s+case"
        r"|if|unless|when|whenever|once|before|after|until|while)\b(?!-)",
        _I,
    ),
    imperative_verbs=frozenset(
        """
        accept acknowledge advise apologise apologize ask assist authenticate block book cancel capture check
        clarify close collect confirm connect create decline direct disclose discuss encourage end ensure
        escalate explain freeze gather give greet guide hand help identify inform introduce keep let listen
        make mention notify obtain offer open promise reassure refuse
        provide quote read recommend remind repeat respond route say schedule send share spell state stay
        suggest summarise summarize take tell thank transfer treat unblock use validate verify warn
        """.split()
    ),
    reporting_verbs=frozenset("ask advise check clarify confirm explain find inform mention say state tell".split()),
    auxiliaries=frozenset("is are was were be been has have had will would can could should must may does do did".split()),
    object_starters=frozenset(
        """
        you they he she it we i me us them him the a an this that these those their your his her its our
        any all every each no whether if what why how when where who which
        """.split()
    ),
    fillers=frozenset("please kindly then also first immediately politely always".split()),
    number_words={
        w: i
        for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())
    },
    count_rewrites=(
        (re.compile(r"\btwice\b", _I), "two times"),
        (re.compile(r"\bthrice\b", _I), "three times"),
    ),
    counter=re.compile(rf"\b{_NUM}\s+(?!of\b)(?P<subject>(?:[a-z][\w'’-]*\s+){{0,3}}?{_UNITS})\b", _I),
    max_marker=re.compile(
        r"\b(?:at\s+most|up\s+to|no\s+more\s+than|not\s+more\s+than|(?:a\s+)?maximum\s+of|max(?:imum)?"
        r"|limit(?:ed)?\s+(?:of|to)|a\s+limit\s+of)\b",
        _I,
    ),
    terminations=(
        (
            re.compile(
                r"\b(?:end|terminate|close|finish|conclude)\s+(?:the|this)\s+"
                r"(?:call|conversation|session|chat|interaction)\b|\bhang\s+up\b|\bdisconnect\b",
                _I,
            ),
            "end",
        ),
        (
            re.compile(
                r"\b(?:transfer|escalate|hand\s+(?:off|over)|route|pass)\b.*?\bto\s+(?:a|an|the)?\s*"
                r"(?:[\w'’-]+\s+){0,2}?(?:human|person|agent|advisor|adviser|representative|specialist"
                r"|supervisor|manager|team|department|colleague|handler|desk|queue|line)s?\b",
                _I,
            ),
            "handoff",
        ),
    ),
    key_hints=(
        (re.compile(r"\b(?:forbidden|prohibited|never|must not|do not|dont|not allowed|disallowed|banned|donts)\b"), "must_not"),
        (re.compile(r"\b(?:should not|avoid|discouraged)\b"), "should_not"),
        (re.compile(r"\b(?:required|must|always|mandatory|dos)\b"), "must"),
        (re.compile(r"\b(?:allowed|permitted|may|optional)\b"), "may"),
    ),
    counter_keys=re.compile(r"\b(?:max|maximum|limit|limits|attempts?|retries|retry|tries)\b"),
    limit_keys=re.compile(r"\b(?:max|maximum|limit|limits)\b"),
)
