from __future__ import annotations

import httpx
import json
import random
import re
import time
from typing import Any, Dict
from openai import OpenAI


def _strip_provider(model: str) -> str:
    return model.split("/", 1)[1] if "/" in model else model


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        blob = fenced.group(1).strip()
    else:
        m = re.search(r"\{.*?\}", text, re.S)
        if not m:
            raise ValueError("Model did not return JSON")
        blob = m.group(0).strip()

    blob = re.sub(r'\\\\(?!["\\\\/bfnrtu])', r"\\\\\\\\", blob)
    return json.loads(blob)


class OpenAIClient:
    def __init__(self) -> None:
        timeout = httpx.Timeout(60.0, connect=10.0, read=60.0, write=60.0, pool=10.0)
        self.client = OpenAI(http_client=httpx.Client(timeout=timeout))

    def _responses_create_with_retry(self, *, model: str, system: str, user: str, max_tries: int = 3) -> Any:
        last_err: Exception | None = None
        for attempt in range(1, max_tries + 1):
            try:
                return self.client.responses.create(
                    model=_strip_provider(model),
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
            except Exception as e:
                last_err = e
                if attempt < max_tries:
                    sleep_s = min(8.0, 0.8 * (2 ** (attempt - 1))) + random.random() * 0.25
                    time.sleep(sleep_s)
        raise last_err  # type: ignore

    def call_text(self, model: str, system: str, user: str, *, max_tries: int = 3) -> str:
        resp = self._responses_create_with_retry(model=model, system=system, user=user, max_tries=max_tries)
        return (getattr(resp, "output_text", "") or "").strip()

    def call_json(self, model: str, system: str, user: str, *, max_tries: int = 3) -> dict:
        txt = self.call_text(model, system, user, max_tries=max_tries)
        return _extract_json(txt)

    def call_text_safe(self, model: str, system: str, user: str, *, max_tries: int = 2, fallback: str = "") -> str:
        try:
            return self.call_text(model, system, user, max_tries=max_tries)
        except Exception:
            return fallback
