from __future__ import annotations

import unittest

import httpx

from worktrace.ocr.client import OCRError, extract_ocr_text, paddle_health_url, parse_ocr_json


class OCRClientTests(unittest.TestCase):
    def test_extracts_text_from_paddle_json_documents(self) -> None:
        payload = {
            "ok": True,
            "documents": [
                {
                    "doc_id": "screen",
                    "pages": [
                        {
                            "page_no": 1,
                            "texts": ["客户需求确认", "接口联调"],
                            "full_text": "客户需求确认\n接口联调",
                        }
                    ],
                    "full_text": "客户需求确认\n接口联调",
                }
            ],
        }

        self.assertEqual(extract_ocr_text(payload), "客户需求确认\n接口联调")

    def test_builds_paddle_health_url_from_ocr_url(self) -> None:
        self.assertEqual(
            paddle_health_url("http://192.168.8.29:8866/ocr"),
            "http://192.168.8.29:8866/health",
        )

    def test_invalid_ocr_json_becomes_fallback_error(self) -> None:
        response = httpx.Response(
            200,
            text="gateway returned html",
            request=httpx.Request("POST", "http://127.0.0.1/ocr"),
        )

        with self.assertRaisesRegex(OCRError, "invalid JSON"):
            parse_ocr_json(response)
        self.assertEqual(
            paddle_health_url("http://192.168.8.29:8866"),
            "http://192.168.8.29:8866/health",
        )


if __name__ == "__main__":
    unittest.main()
