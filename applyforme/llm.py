from __future__ import annotations

import json
import os
import re
import time
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .config import MODEL

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


def client() -> OpenAI:
    """Provider is picked from env: GEMINI_API_KEY (free tier) wins, else OPENAI_API_KEY / OPENAI_BASE_URL."""
    global _client
    if _client is None:
        if os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            _client = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_BASE)
        else:
            _client = OpenAI()
    return _client


def _extract_json(text: str) -> str:
    """Tolerate models that wrap JSON in ```fences``` or add prose."""
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


def ask_json(system: str, user: str, schema: type[T], temperature: float = 0.2, retries: int = 3) -> T:
    """Call the LLM and parse the reply into a pydantic model (with retry/backoff for rate limits)."""
    messages = [
        {
            "role": "system",
            "content": system + "\n\nReply with a single JSON object matching this schema:\n" + json.dumps(schema.model_json_schema()),
        },
        {"role": "user", "content": user},
    ]
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client().chat.completions.create(
                model=MODEL, temperature=temperature, response_format={"type": "json_object"}, messages=messages
            )
            return schema.model_validate_json(_extract_json(resp.choices[0].message.content))
        except Exception as e:  # rate limit (free tiers are ~15 RPM) or malformed JSON
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last}")
