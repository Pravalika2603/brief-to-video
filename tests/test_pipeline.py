import json
from pathlib import Path

import pytest

from b2v.llm import LLMResult, MockLLM, parse_script
from b2v.metrics import Metrics
from b2v.models import Brief
from b2v.pipeline import run_brief
from b2v.publish import DryRunPublisher
from b2v.storage import LocalStorage

BRIEF = Brief.from_dict(json.loads((Path(__file__).parents[1] / "examples" / "brief.json").read_text()))


def _run(tmp_path, llm, **kw):
    return run_brief(BRIEF, llm, tmp_path, DryRunPublisher(tmp_path / "queue"),
                     LocalStorage(tmp_path), Metrics(tmp_path / "m.db"), **kw)


def test_happy_path_renders_valid_mp4_and_queues_post(tmp_path):
    r = _run(tmp_path, MockLLM())
    assert r.approved and r.attempts == 1
    data = Path(r.video_path).read_bytes()
    assert len(data) > 10_000 and b"ftyp" in data[:32]
    assert (tmp_path / "queue" / f"{BRIEF.brief_id}.json").exists()


def test_qa_feedback_loop_recovers_from_bad_first_draft(tmp_path):
    r = _run(tmp_path, MockLLM(flawed_first_attempt=True))
    assert r.approved and r.attempts == 2


def test_gives_up_after_max_attempts_and_logs_rejection(tmp_path):
    class AlwaysBad:
        def complete(self, system, user):
            return LLMResult(json.dumps({"hook": "Unlock it", "body": ["a"], "cta": "", "caption": ""}))

    r = _run(tmp_path, AlwaysBad(), max_attempts=2)
    assert not r.approved and r.attempts == 2 and r.issues
    assert Metrics(tmp_path / "m.db").summary()["approved"] == 0


def test_cost_per_approved_post_is_tracked(tmp_path):
    _run(tmp_path, MockLLM(flawed_first_attempt=True))
    s = Metrics(tmp_path / "m.db").summary()
    assert s["approved"] == 1 and s["cost_per_approved_post_usd"] > 0


def test_parse_script_handles_code_fences_and_rejects_garbage():
    fenced = '```json\n{"hook":"h","body":["a","b","c"],"cta":"go","caption":"c"}\n```'
    assert parse_script(fenced).hook == "h"
    with pytest.raises(ValueError):
        parse_script("not json at all")
