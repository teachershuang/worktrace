from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from worktrace.config.settings import LLMSettings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM service request fails."""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMClient:
    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [message.__dict__ for message in messages],
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        try:
            with httpx.Client(timeout=self.settings.timeout_seconds, trust_env=self.settings.trust_env) as client:
                response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("LLM request failed")
            raise LLMError(f"LLM request failed: {exc}") from exc

        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected LLM response shape: {json.dumps(data, ensure_ascii=False)[:500]}") from exc

    def chat_json(self, messages: list[ChatMessage], *, temperature: float = 0.1) -> dict[str, Any]:
        content = self.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(extract_json_object(content))
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM did not return valid JSON: {content[:500]}") from exc

    def test_connection(self) -> tuple[bool, str]:
        try:
            content = self.chat(
                [
                    ChatMessage(role="system", content="You are a connectivity test endpoint."),
                    ChatMessage(role="user", content="Reply with OK only."),
                ],
                temperature=0,
            )
            return True, content.strip()
        except LLMError as exc:
            return False, str(exc)


def extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped
