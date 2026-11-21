# brief-to-video

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

A small, tested Python pipeline that turns a client brief into a scheduled short-form vertical video, with an automated quality gate and cost-per-approved-post tracking.

I built it to demonstrate the engineering side of AI-driven social content: many moving parts (LLM, media, storage, publishing APIs), where the hard problem is **reliability and quality control at volume**, not a single clever prompt.

```
brief.json -> LLM script -> QA gate -+-> fail: feed issues back, retry (max N)
                                      |
                                      +-> pass: render 1080x1920 MP4 (Pillow + FFmpeg)
                                                -> store (local / GCS) -> schedule (dry-run) -> log metrics (SQLite)
```

## Quick start

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m b2v examples/brief.json --demo-retry -v
PYTHONPATH=src pytest -q
```

No API key needed: without `ANTHROPIC_API_KEY` it uses a deterministic mock LLM. `--demo-retry` makes the first draft deliberately bad so you can watch the QA loop work:

```
WARNING attempt 1 rejected: slop phrase used: 'game-changer'; slop phrase used: 'unlock'; ...
INFO    attempt 2 approved
[APPROVED] lumen-subscription-01: attempts=2 cost=$0.00299 video=out/videos/lumen-subscription-01.mp4 ...
summary: {"runs": 1, "approved": 1, "cost_per_approved_post_usd": 0.002988, "approval_rate": 1.0}
```

To use a real model: `export ANTHROPIC_API_KEY=...` (optionally `B2V_MODEL`, and set `B2V_PRICE_IN_PER_MTOK` / `B2V_PRICE_OUT_PER_MTOK` to current pricing so cost tracking is accurate).

## What it does

| Concern | Where | Notes |
|---|---|---|
| LLM integration | `llm.py` | REST client for the Anthropic Messages API; retries 429/5xx with exponential backoff, fails fast on auth errors; token-based cost tracking |
| Quality gate | `quality.py` | Rejects AI-slop phrases, wordy hooks, bad pacing/duration, and **invented claims** (any number in the copy must appear in the brief) |
| Self-correction | `pipeline.py` | QA issues are fed back to the model as feedback for the next attempt |
| Media | `render.py` | Pillow draws branded 1080x1920 frames; FFmpeg builds the MP4 (fades, H.264, AAC track) with a bundled-binary fallback |
| Storage | `storage.py` | Local by default; `GCSStorage` for Google Cloud Storage (`requirements-gcs.txt`) |
| Publishing | `publish.py` | `Publisher` interface + dry-run implementation that writes the exact payload it would send |
| Observability | `metrics.py` | SQLite log of attempts, approval, cost; reports **cost per approved post** and approval rate |
| CI | `.github/workflows/ci.yml` | Runs the test suite (including a real FFmpeg render) on every push |

## Design decisions

- **QA before render.** Rendering is the expensive step, so bad scripts are rejected on cheap text checks first.
- **Facts come from the brief only.** The prompt forbids invented claims and the gate enforces it, since product inaccuracies are a real brand risk.
- **Offline-first.** The mock LLM and dry-run publisher mean the whole flow is testable in CI with no secrets and no network.
- **Narrow interfaces** (`LLM`, `Storage`, `Publisher`) so each integration can be swapped without touching the pipeline.

## Limitations (honest list)

- Visuals are text-on-gradient scenes. A production system would add generated or stock footage, voiceover and music, and use per-platform aspect ratios.
- `InstagramPublisher` is an intentionally unimplemented stub. Real posting needs the platform's official API and OAuth 2.0 tokens held in a secret manager, and this demo does not post to real accounts.
- The QA gate is rule-based. It doesn't judge creative quality; a next step would be an LLM-as-judge check plus performance-data feedback.
- Cost figures use configurable placeholder prices.

## Next steps

Performance-data ingestion (views, retention) feeding back into prompts, an A/B hook-variant generator, a batch runner with concurrency, and a real publisher behind the existing interface.

## Layout

```
src/b2v/   models, llm, quality, render, storage, publish, metrics, pipeline, cli
tests/     QA rules, pipeline end-to-end (real MP4), retry loop, metrics
examples/  sample brief
```
