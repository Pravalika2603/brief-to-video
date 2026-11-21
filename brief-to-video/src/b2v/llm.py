"""LLM access: a real Anthropic client with retries + cost tracking, and an offline mock."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol

import requests

from .models import Brief, Script

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.getenv("B2V_MODEL", "claude-sonnet-5-5")

# Per-million-token prices. These are placeholders: set them to your model's
# current pricing so cost-per-approved-post is accurate.
PRICE_IN = float(os.getenv("B2V_PRICE_IN_PER_MTOK", "3.0"))
PRICE_OUT = float(os.getenv("B2V_PRICE_OUT_PER_MTOK", "15.0"))

SYSTEM_PROMPT = """You write short-form social video scripts for a marketing agency.
Rules:
- Return ONLY a JSON object, no prose, no code fences.
- Schema: {"hook": str, "body": [str, ...], "cta": str, "caption": str, "hashtags": [str, ...]}
- hook: max 10 words, specific, no clickbait.
- body: 3 to 5 scenes, each max 14 words.
- Use ONLY facts and numbers from the brief. Never invent claims.
- Avoid hype and filler words such as "game-changer", "unlock", "revolutionary".
- Match the requested tone."""


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_IN + self.output_tokens * PRICE_OUT) / 1_000_000


class LLM(Protocol):
    def complete(self, system: str, user: str) -> LLMResult: ...


def build_user_prompt(brief: Brief, feedback: Optional[List[str]] = None) -> str:
    parts = [
        f"Brand: {brief.brand}",
        f"Product: {brief.product}",
        f"Audience: {brief.audience}",
        f"Tone: {brief.tone}",
        "Facts you may use:",
        *[f"- {f}" for f in brief.facts],
        f"Call to action: {brief.cta}",
    ]
    if feedback:
        parts += ["", "Your previous draft failed review. Fix these issues:", *[f"- {i}" for i in feedback]]
    return "\n".join(parts)


class AnthropicLLM:
    """Minimal Messages API client: retries 429/5xx with exponential backoff."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 max_retries: int = 3, timeout: int = 60, max_tokens: int = 800):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self.model, self.max_retries, self.timeout, self.max_tokens = model, max_retries, timeout, max_tokens

    def complete(self, system: str, user: str) -> LLMResult:
        payload = {"model": self.model, "max_tokens": self.max_tokens, "system": system,
                   "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(API_URL, headers=headers, json=payload, timeout=self.timeout)
            except requests.RequestException as e:
                last = str(e)
            else:
                if r.status_code == 200:
                    data = r.json()
                    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
                    usage = data.get("usage", {})
                    return LLMResult(text, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code not in (429, 500, 502, 503, 529):
                    raise LLMError(last)  # non-retryable (auth, bad request)
            time.sleep(min(2 ** attempt, 20))
        raise LLMError(f"LLM failed after {self.max_retries + 1} attempts: {last}")


class MockLLM:
    """Deterministic offline generator so the project runs (and tests) without an API key.

    flawed_first_attempt=True makes draft #1 intentionally bad, to demo the QA retry loop.
    """

    def __init__(self, flawed_first_attempt: bool = False):
        self.flawed_first_attempt = flawed_first_attempt
        self.calls = 0

    def complete(self, system: str, user: str) -> LLMResult:
        self.calls += 1
        lines = user.splitlines()
        get = lambda k: next((l.split(": ", 1)[1] for l in lines if l.startswith(k + ": ")), "")
        brand, product, cta = get("Brand"), get("Product"), get("Call to action")
        audience = get("Audience")
        facts = [l[2:] for l in lines if l.startswith("- ") and "failed review" not in l]
        if "previous draft failed review" in user:
            facts = [f for f in facts if f in user.split("Fix these issues:")[0]]
        if self.flawed_first_attempt and self.calls == 1:
            data = {"hook": "Unlock the game-changer your mornings need!", "body": facts[:3],
                    "cta": cta, "caption": f"{brand} is revolutionary.", "hashtags": ["#coffee"]}
        else:
            tag = "#" + re.sub(r"\W+", "", brand)
            data = {"hook": f"Made for {audience}.", "body": facts[:4], "cta": cta,
                    "caption": f"{brand}: {product}. {facts[0] if facts else ''}".strip(),
                    "hashtags": [tag, "#" + re.sub(r"\W+", "", product.split()[0])]}
        text = json.dumps(data)
        return LLMResult(text, input_tokens=len(user.split()) * 2, output_tokens=len(text.split()) * 2)


def parse_script(text: str) -> Script:
    """Parse model output into a Script; tolerant of code fences, strict on shape."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        d = json.loads(cleaned)
        return Script(hook=str(d["hook"]).strip(), body=[str(s).strip() for s in d["body"]],
                      cta=str(d["cta"]).strip(), caption=str(d.get("caption", "")).strip(),
                      hashtags=[str(h).strip() for h in d.get("hashtags", [])])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"model output is not valid script JSON ({e})") from e
