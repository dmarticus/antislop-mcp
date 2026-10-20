"""Small OpenAI-compatible client for a local Antislop server."""

from __future__ import annotations

import os
from typing import Any

import httpx


class AntislopError(RuntimeError):
    """An inference request could not be completed."""


class AntislopClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("ANTISLOP_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
        self.model = os.getenv("ANTISLOP_MODEL", "antislop")
        self.api_key = os.getenv("ANTISLOP_API_KEY", "local")
        # Dense local models can need several minutes to rewrite a long document.
        self.timeout = float(os.getenv("ANTISLOP_TIMEOUT", "240"))

    async def status(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/models")
                response.raise_for_status()
                models = response.json().get("data", [])
            ids = [item.get("id") for item in models]
            return {"status": "ready", "endpoint": self.base_url, "model": self.model, "models": ids}
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "status": "unavailable",
                "endpoint": self.base_url,
                "model": self.model,
                "message": f"Antislop is unavailable: {exc}",
            }

    async def complete(
        self,
        *,
        text: str,
        instruction: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Antislop, a careful editor. Make prose sound like a specific human wrote it. "
                        "Prefer concrete details, natural rhythm, plain words, and an earned voice. Remove generic "
                        "AI phrasing, inflated claims, unnecessary headings, fake enthusiasm, and tidy summary "
                        "endings. Preserve the author's meaning, facts, names, numbers, links, formatting, and "
                        "intent. Output only the edited text, with no preamble or commentary."
                    ),
                },
                {"role": "user", "content": f"{instruction}\n\nTEXT:\n{text}"},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AntislopError("The model returned no text.")
            return strip_thinking(content).strip()
        except httpx.TimeoutException as exc:
            raise AntislopError(
                f"Antislop timed out after {self.timeout:g} seconds. "
                "Retry with less text or a lower max_tokens value; split long documents at "
                "heading or paragraph boundaries."
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise AntislopError(f"Antislop request failed: {detail}") from exc


def strip_thinking(text: str) -> str:
    """Defensively remove reasoning markers from runners that ignore thinking-off flags."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    while "<think>" in text and "</think>" in text:
        start = text.index("<think>")
        end = text.index("</think>", start) + len("</think>")
        text = text[:start] + text[end:]
    return text
