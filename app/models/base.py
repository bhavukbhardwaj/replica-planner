from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Model provider failed (timeout, HTTP error, malformed envelope)."""


@dataclass
class ModelTurn:
    content: str | None = None
    tool_calls: list[dict] = field(default_factory=list)  # [{"id", "name", "arguments": dict|str}]


class ModelClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...
