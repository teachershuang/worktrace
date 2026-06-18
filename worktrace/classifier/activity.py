from __future__ import annotations

import logging
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from worktrace.capture.screen import ActiveWindow
from worktrace.llm.client import ChatMessage, LLMClient, LLMError
from worktrace.prompts import load_prompt

logger = logging.getLogger(__name__)

ActivityCategory = Literal[
    "工作沟通",
    "开发编码",
    "调试排错",
    "文档编写",
    "资料调研",
    "方案设计",
    "测试验证",
    "部署运维",
    "项目管理",
    "其他",
]


class ActivityDecision(BaseModel):
    should_record: bool
    is_work: bool
    category: ActivityCategory = "其他"
    project: str | None = None
    title: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    need_review: bool
    skip_reason: str | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        return value.strip()[:40]

    @field_validator("summary")
    @classmethod
    def trim_summary(cls, value: str) -> str:
        return value.strip()[:160]

    @field_validator("project")
    @classmethod
    def trim_project(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


@dataclass(frozen=True)
class ClassificationContext:
    captured_at: datetime
    active_window: ActiveWindow
    ocr_text: str
    previous_event: dict[str, Any] | None
    recent_summary: str
    project_names_today: list[str]
    ocr_error: str | None = None


class ActivityClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.prompt = load_prompt("classify_activity.md")

    def classify(self, context: ClassificationContext) -> ActivityDecision:
        user_content = build_user_content(context)
        try:
            data = self.llm.chat_json(
                [
                    ChatMessage(role="system", content=self.prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0.1,
            )
            decision = ActivityDecision.model_validate(data)
        except (LLMError, ValidationError) as exc:
            logger.exception("activity classification failed")
            raise

        if decision.confidence < 0.6 and decision.should_record:
            decision = decision.model_copy(update={"should_record": False, "need_review": True})
        return decision


def build_user_content(context: ClassificationContext) -> str:
    payload = {
        "current_time": context.captured_at.isoformat(timespec="seconds"),
        "app_name": context.active_window.app_name,
        "window_title": context.active_window.title,
        "ocr_text": context.ocr_text[:6000],
        "ocr_error": context.ocr_error,
        "previous_valid_work_event": context.previous_event,
        "recent_30_minute_summary": context.recent_summary,
        "project_names_today": context.project_names_today,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def decision_to_dict(decision: ActivityDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")


def context_to_dict(context: ClassificationContext) -> dict[str, Any]:
    return {
        "captured_at": context.captured_at.isoformat(),
        "active_window": asdict(context.active_window),
        "ocr_text": context.ocr_text,
        "ocr_error": context.ocr_error,
        "previous_event": context.previous_event,
        "recent_summary": context.recent_summary,
        "project_names_today": context.project_names_today,
    }
