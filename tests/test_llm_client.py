from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from worktrace.config.settings import LLMSettings
from worktrace.llm.client import ChatMessage, LLMClient


class LLMClientTests(unittest.TestCase):
    def test_unauthorized_error_is_actionable(self) -> None:
        client = LLMClient(
            LLMSettings(
                base_url="http://127.0.0.1:4000/v1",
                api_key="bad-key",
                model="test-model",
            )
        )

        with patch("worktrace.llm.client.httpx.Client", return_value=FakeClient(401, '{"detail":"bad key"}')):
            ok, message = client.test_connection()

        self.assertFalse(ok)
        self.assertIn("authentication failed", message)
        self.assertIn("llm.api_key", message)
        self.assertNotIn("chat/completions", message)


class FakeClient:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, **_kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(self.status_code, text=self.text, request=request)


if __name__ == "__main__":
    unittest.main()
