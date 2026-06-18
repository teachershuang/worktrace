from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from worktrace.llm.client import ChatMessage, LLMClient, LLMError
from worktrace.prompts import load_prompt
from worktrace.timeline.merge import TimelineItem, merge_events
from worktrace.timeline.store import EventStore

logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self, llm: LLMClient, store: EventStore, output_dir: Path):
        self.llm = llm
        self.store = store
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_daily_report(self, day: date | None = None) -> Path:
        target_day = day or datetime.now().date()
        timeline = merge_events(self.store.load_effective(target_day))
        if not timeline:
            raise RuntimeError("no effective work events found for daily report")

        prompt = load_prompt("generate_daily_report.md")
        content = self._generate(prompt, render_timeline(timeline))
        path = self.output_dir / f"{target_day.isoformat()}-daily.md"
        path.write_text(content, encoding="utf-8")
        return path

    def build_weekly_report(self, day: date | None = None) -> Path:
        target_day = day or datetime.now().date()
        start = target_day - timedelta(days=target_day.weekday())
        end = start + timedelta(days=6)
        timeline = merge_events(self.store.load_effective_between(start, end))
        daily_reports = read_existing_daily_reports(self.output_dir, start, end)
        if not timeline and not daily_reports:
            raise RuntimeError("no effective work events or daily reports found for weekly report")

        prompt = load_prompt("generate_weekly_report.md")
        user_content = "\n\n".join(
            [
                "# 本周时间轴",
                render_timeline(timeline) if timeline else "无",
                "# 已生成日报",
                "\n\n".join(daily_reports) if daily_reports else "无",
            ]
        )
        content = self._generate(prompt, user_content)
        path = self.output_dir / f"{start.isoformat()}_to_{end.isoformat()}-weekly.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _generate(self, system_prompt: str, user_content: str) -> str:
        try:
            return self.llm.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0.2,
            ).strip()
        except LLMError:
            logger.exception("report generation failed")
            raise


def render_timeline(items: list[TimelineItem]) -> str:
    lines = []
    for item in items:
        project = item.project or "未识别项目"
        lines.append(
            f"- {item.start_at:%H:%M}-{item.end_at:%H:%M} "
            f"[{project}/{item.category}] {item.title}: {item.summary}"
        )
    return "\n".join(lines)


def read_existing_daily_reports(output_dir: Path, start: date, end: date) -> list[str]:
    reports: list[str] = []
    current = start
    while current <= end:
        path = output_dir / f"{current.isoformat()}-daily.md"
        if path.exists():
            reports.append(f"## {current.isoformat()}\n{path.read_text(encoding='utf-8')}")
        current += timedelta(days=1)
    return reports
