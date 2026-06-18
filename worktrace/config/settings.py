from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class ConfigError(RuntimeError):
    """Raised when WorkTrace configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class WorkPeriod:
    start: time
    end: time

    def contains(self, value: time) -> bool:
        return self.start <= value <= self.end


class LLMSettings(BaseModel):
    base_url: str = Field(min_length=1)
    api_key: str = ""
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60, gt=0)
    trust_env: bool = False


class OCRSettings(BaseModel):
    url: str = Field(min_length=1)
    timeout_seconds: float = Field(default=30, gt=0)
    protocol: Literal["multipart", "paddle_json"] = "multipart"
    trust_env: bool = False


class RecordingSettings(BaseModel):
    work_periods: list[str] = Field(default_factory=lambda: ["09:00-12:00", "13:30-18:00"])
    screenshot_interval_seconds: int = Field(default=300, gt=0)
    idle_skip_minutes: int = Field(default=10, ge=0)
    enable_tray: bool = False

    @field_validator("work_periods")
    @classmethod
    def validate_work_periods(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("recording.work_periods must contain at least one period")
        for item in value:
            parse_work_period(item)
        return value

    def parsed_periods(self) -> list[WorkPeriod]:
        return [parse_work_period(item) for item in self.work_periods]


class StorageSettings(BaseModel):
    data_dir: Path = Path("data")
    report_output_dir: Path = Path("data/reports")
    log_dir: Path = Path("logs")


class AppSettings(BaseModel):
    llm: LLMSettings
    ocr: OCRSettings
    recording: RecordingSettings = Field(default_factory=RecordingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    def ensure_directories(self) -> None:
        self.storage.data_dir.mkdir(parents=True, exist_ok=True)
        (self.storage.data_dir / "events").mkdir(parents=True, exist_ok=True)
        self.storage.report_output_dir.mkdir(parents=True, exist_ok=True)
        self.storage.log_dir.mkdir(parents=True, exist_ok=True)


def parse_hhmm(value: str) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except Exception as exc:
        raise ValueError(f"invalid time value: {value!r}, expected HH:MM") from exc


def parse_work_period(value: str) -> WorkPeriod:
    try:
        start_raw, end_raw = value.split("-", 1)
    except ValueError as exc:
        raise ValueError(f"invalid work period: {value!r}, expected HH:MM-HH:MM") from exc

    start = parse_hhmm(start_raw.strip())
    end = parse_hhmm(end_raw.strip())
    if start >= end:
        raise ValueError(f"invalid work period: {value!r}, start must be before end")
    return WorkPeriod(start=start, end=end)


def load_config(path: str | Path = "config.yaml") -> AppSettings:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"config file not found: {config_path}. Copy config.example.yaml to config.yaml first."
        )

    try:
        data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"failed to parse YAML config: {config_path}") from exc

    try:
        settings = AppSettings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc

    settings.ensure_directories()
    return settings
