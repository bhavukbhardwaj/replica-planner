"""OpenAI-compatible chat client (works with Ollama's /v1 endpoint)."""
import json
import os

import httpx

from app.models.base import ModelTurn, ProviderError


class OpenAICompatModel:
    def __init__(self, base_url: str, model: str, timeout_s: float = 60):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout_s
        key = os.environ.get("MODEL_API_KEY")  # optional; env only, never logged
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    def chat(self, messages, tools):
        body = {"model": self.model, "messages": messages, "tools": tools, "temperature": 0}
        try:
            r = httpx.post(self.url, json=body, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(type(e).__name__) from None  # no URL/headers in message
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            calls.append({"id": tc.get("id") or str(i), "name": fn.get("name", ""),
                          "arguments": fn.get("arguments", {})})
        return ModelTurn(content=msg.get("content"), tool_calls=calls)
