"""Automated QA gate: catches AI slop, bad pacing, and invented product claims."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .models import Brief, Script

SLOP_PHRASES = [
    "game-changer", "game changer", "unlock", "revolutionary", "in today's fast-paced world",
    "delve", "elevate your", "supercharge", "seamless", "cutting-edge", "unleash", "next level",
]
MAX_HOOK_WORDS = 10
MAX_SCENE_WORDS = 14
BODY_RANGE = (3, 5)
DURATION_RANGE = (10.0, 45.0)
MAX_HASHTAGS = 5
_NUM = re.compile(r"\d[\d,.]*")


@dataclass
class QAReport:
    issues: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _numbers(text: str) -> set:
    return {n.strip(".,") for n in _NUM.findall(text)}


def check_script(script: Script, brief: Brief) -> QAReport:
    r = QAReport()
    full = " ".join([*script.scene_texts(), script.caption]).lower()

    for phrase in SLOP_PHRASES:
        if phrase in full:
            r.issues.append(f"slop phrase used: '{phrase}'")

    if len(script.hook.split()) > MAX_HOOK_WORDS:
        r.issues.append(f"hook too long ({len(script.hook.split())} words, max {MAX_HOOK_WORDS})")
    if not (BODY_RANGE[0] <= len(script.body) <= BODY_RANGE[1]):
        r.issues.append(f"body must have {BODY_RANGE[0]}-{BODY_RANGE[1]} scenes, got {len(script.body)}")
    for i, s in enumerate(script.scene_texts()):
        if len(s.split()) > MAX_SCENE_WORDS:
            r.issues.append(f"scene {i + 1} too wordy ({len(s.split())} words, max {MAX_SCENE_WORDS})")
    total = script.total_seconds()
    if not (DURATION_RANGE[0] <= total <= DURATION_RANGE[1]):
        r.issues.append(f"duration {total}s outside {DURATION_RANGE[0]}-{DURATION_RANGE[1]}s")
    if not script.cta.strip():
        r.issues.append("missing call to action")
    if len(script.hashtags) > MAX_HASHTAGS:
        r.issues.append(f"too many hashtags ({len(script.hashtags)}, max {MAX_HASHTAGS})")

    # Product-accuracy check: every number in the copy must come from the brief.
    allowed = _numbers(" ".join([*brief.facts, brief.product, brief.brand, brief.cta]))
    for n in sorted(_numbers(full) - allowed):
        r.issues.append(f"number '{n}' does not appear in the brief (possible invented claim)")
    return r
