from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worktrace.capture.screen import ScreenCapture
from worktrace.classifier.activity import ActivityClassifier
from worktrace.config.logging import setup_logging
from worktrace.config.settings import AppSettings, load_config
from worktrace.llm.client import LLMClient
from worktrace.ocr.client import OCRClient
from worktrace.report.generator import ReportGenerator
from worktrace.runtime.recorder import WorkRecorder
from worktrace.runtime.state import RuntimeStateStore
from worktrace.timeline.store import EventStore


@dataclass(frozen=True)
class AppContext:
    settings: AppSettings
    llm: LLMClient
    ocr: OCRClient
    store: EventStore
    state_store: RuntimeStateStore
    recorder: WorkRecorder
    reports: ReportGenerator


def build_app_context(config_path: Path, verbose: bool = False) -> AppContext:
    settings = load_config(config_path)
    setup_logging(settings.storage.log_dir, verbose=verbose)
    llm = LLMClient(settings.llm)
    ocr = OCRClient(settings.ocr)
    store = EventStore(settings.storage.data_dir)
    state_store = RuntimeStateStore(settings.storage.data_dir / "runtime_state.json")
    recorder = WorkRecorder(
        capture=ScreenCapture(),
        ocr=ocr,
        classifier=ActivityClassifier(llm),
        store=store,
    )
    reports = ReportGenerator(
        llm=llm,
        store=store,
        output_dir=settings.storage.report_output_dir,
    )
    return AppContext(
        settings=settings,
        llm=llm,
        ocr=ocr,
        store=store,
        state_store=state_store,
        recorder=recorder,
        reports=reports,
    )
