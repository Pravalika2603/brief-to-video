"""Orchestration: generate -> QA gate (with feedback retries) -> render -> store -> schedule -> log."""
from __future__ import annotations

import logging
from pathlib import Path

from .llm import LLM, SYSTEM_PROMPT, LLMError, build_user_prompt, parse_script
from .metrics import Metrics
from .models import Brief, PostResult
from .publish import Publisher, next_slot
from .quality import check_script
from .render import render_video
from .storage import Storage

log = logging.getLogger("b2v")


def run_brief(brief: Brief, llm: LLM, out_dir: Path, publisher: Publisher, storage: Storage,
              metrics: Metrics, max_attempts: int = 3) -> PostResult:
    feedback, cost, issues, script = None, 0.0, [], None
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        try:
            res = llm.complete(SYSTEM_PROMPT, build_user_prompt(brief, feedback))
        except LLMError as e:
            issues = [f"llm error: {e}"]
            log.error("attempt %d: %s", attempts, e)
            break
        cost += res.cost_usd
        try:
            candidate = parse_script(res.text)
        except ValueError as e:
            feedback = issues = [str(e)]
            log.warning("attempt %d rejected: %s", attempts, e)
            continue
        report = check_script(candidate, brief)
        if report.ok:
            script, issues = candidate, []
            log.info("attempt %d approved", attempts)
            break
        feedback = issues = report.issues
        log.warning("attempt %d rejected: %s", attempts, "; ".join(report.issues))

    if script is None:
        result = PostResult(brief.brief_id, False, attempts, round(cost, 6), issues)
        metrics.record(result)
        return result

    local = render_video(script, brief.brand, Path(out_dir) / "videos" / f"{brief.brief_id}.mp4")
    stored = storage.upload(local, f"videos/{brief.brief_id}.mp4")
    when = next_slot()
    publisher.schedule(stored, script.caption, script.hashtags, when)
    result = PostResult(brief.brief_id, True, attempts, round(cost, 6), [], stored, when.isoformat())
    metrics.record(result)
    return result
