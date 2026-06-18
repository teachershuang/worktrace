from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from worktrace.config.settings import OCRSettings

logger = logging.getLogger(__name__)


class OCRError(RuntimeError):
    """Raised when OCR service invocation fails."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class OCRClient:
    def __init__(self, settings: OCRSettings):
        self.settings = settings

    def recognize_png(self, image_bytes: bytes) -> OCRResult:
        files = {"file": ("screenshot.png", image_bytes, "image/png")}
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(self.settings.url, files=files)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("OCR request failed")
            raise OCRError(f"OCR request failed: {exc}") from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            return OCRResult(text=extract_ocr_text(data), raw=data)

        return OCRResult(text=response.text.strip(), raw={"text": response.text})

    def test_connection(self) -> tuple[bool, str]:
        # A minimal invalid PNG is still useful for testing reachability. Services may
        # return a 4xx for invalid image data, which proves the endpoint is alive.
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(
                    self.settings.url,
                    files={"file": ("empty.png", b"", "image/png")},
                )
            if response.status_code < 500:
                return True, f"HTTP {response.status_code}: OCR endpoint reachable"
            return False, f"HTTP {response.status_code}: {response.text[:300]}"
        except httpx.HTTPError as exc:
            return False, f"OCR endpoint unreachable: {exc}"


def extract_ocr_text(data: dict[str, Any]) -> str:
    for key in ("text", "content", "result", "ocr_text"):
        value = data.get(key)
        if isinstance(value, str):
            return value.strip()

    lines = data.get("lines")
    if isinstance(lines, list):
        parts = []
        for line in lines:
            if isinstance(line, str):
                parts.append(line)
            elif isinstance(line, dict):
                text = line.get("text") or line.get("content")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    boxes = data.get("boxes")
    if isinstance(boxes, list):
        parts = []
        for box in boxes:
            if isinstance(box, dict):
                text = box.get("text") or box.get("content")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    return ""
