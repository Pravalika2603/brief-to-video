from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from .llm import AnthropicLLM, MockLLM
from .metrics import Metrics
from .models import Brief
from .pipeline import run_brief
from .publish import DryRunPublisher
from .storage import LocalStorage


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="b2v", description="Turn a client brief into a scheduled short-form video.")
    p.add_argument("briefs", nargs="+", help="path(s) to brief JSON files")
    p.add_argument("--out", default="out", help="output directory")
    p.add_argument("--mock", action="store_true", help="use the offline mock LLM (default if no API key)")
    p.add_argument("--demo-retry", action="store_true", help="mock LLM writes a flawed first draft to show the QA retry loop")
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    use_mock = a.mock or a.demo_retry or not os.getenv("ANTHROPIC_API_KEY")
    out = Path(a.out)
    metrics = Metrics(out / "metrics.db")
    publisher, storage = DryRunPublisher(out / "queue"), LocalStorage(out)

    for path in a.briefs:
        brief = Brief.from_dict(json.loads(Path(path).read_text()))
        llm = MockLLM(flawed_first_attempt=a.demo_retry) if use_mock else AnthropicLLM()
        r = run_brief(brief, llm, out, publisher, storage, metrics, a.max_attempts)
        status = "APPROVED" if r.approved else "REJECTED"
        print(f"[{status}] {r.brief_id}: attempts={r.attempts} cost=${r.cost_usd:.5f}"
              + (f" video={r.video_path} scheduled={r.scheduled_for}" if r.approved else f" issues={r.issues}"))
    print("summary:", json.dumps(metrics.summary()))
    return 0
