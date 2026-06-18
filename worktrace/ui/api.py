from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from worktrace.capture.idle import get_idle_seconds
from worktrace.runtime.app_context import AppContext, build_app_context
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.runtime.time_windows import is_within_work_periods
from worktrace.timeline.merge import merge_events

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ConsoleRuntime:
    def __init__(self, context: AppContext):
        self.context = context
        self._loop_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start_loop(self) -> bool:
        with self._lock:
            if self._loop_thread and self._loop_thread.is_alive():
                return False
            loop = BackgroundRecorderLoop(
                self.context.settings,
                self.context.recorder,
                self.context.state_store,
            )
            self._loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
            self._loop_thread.start()
            return True

    def loop_running(self) -> bool:
        return bool(self._loop_thread and self._loop_thread.is_alive())


def create_app(config_path: Path = Path("config.yaml"), verbose: bool = False) -> FastAPI:
    context = build_app_context(config_path, verbose=verbose)
    runtime = ConsoleRuntime(context)
    app = FastAPI(title="WorkTrace Local Console", version="0.1.0")
    app.state.runtime = runtime
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        state = context.state_store.load()
        now = datetime.now()
        return {
            "loop_running": runtime.loop_running(),
            "paused": state.paused,
            "stop_requested": state.stop_requested,
            "in_work_period": is_within_work_periods(now, context.settings.recording.parsed_periods()),
            "now": now.isoformat(timespec="seconds"),
            "work_periods": context.settings.recording.work_periods,
            "screenshot_interval_seconds": context.settings.recording.screenshot_interval_seconds,
            "ocr_consecutive_failures": context.recorder.consecutive_ocr_failures,
            "idle_seconds": get_idle_seconds(),
            "idle_skip_minutes": context.settings.recording.idle_skip_minutes,
        }

    @app.post("/api/start")
    def start() -> dict[str, Any]:
        started = runtime.start_loop()
        return {"started": started, "loop_running": runtime.loop_running()}

    @app.post("/api/pause")
    def pause() -> dict[str, bool]:
        context.state_store.pause()
        return {"paused": True}

    @app.post("/api/resume")
    def resume() -> dict[str, bool]:
        context.state_store.resume()
        return {"paused": False}

    @app.post("/api/stop")
    def stop() -> dict[str, bool]:
        context.state_store.request_stop()
        return {"stop_requested": True}

    @app.post("/api/record-once")
    def record_once() -> dict[str, Any]:
        try:
            return context.recorder.record_once()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/timeline/today")
    def today_timeline() -> dict[str, Any]:
        today = datetime.now().date()
        items = merge_events(context.store.load_effective(today))
        return {"date": today.isoformat(), "items": [item.to_dict() for item in items]}

    @app.get("/api/review")
    def review_list() -> dict[str, Any]:
        today = datetime.now().date()
        return {"date": today.isoformat(), "items": context.store.load_review(today)}

    @app.post("/api/review/{event_id_prefix}/work")
    def review_mark_work(event_id_prefix: str) -> dict[str, Any]:
        event, remaining = pop_review_item(context, event_id_prefix)
        classification = dict(event.get("classification", {}))
        classification["should_record"] = True
        classification["is_work"] = True
        classification["need_review"] = False
        classification["skip_reason"] = None
        event["classification"] = classification
        today = datetime.now().date()
        context.store.replace_review(today, remaining)
        context.store.append_effective(event, today)
        return {"id": event.get("id"), "marked": "work"}

    @app.post("/api/review/{event_id_prefix}/nonwork")
    def review_mark_nonwork(event_id_prefix: str) -> dict[str, Any]:
        event, remaining = pop_review_item(context, event_id_prefix)
        context.store.replace_review(datetime.now().date(), remaining)
        return {"id": event.get("id"), "marked": "nonwork"}

    @app.post("/api/reports/daily")
    def daily_report() -> dict[str, str]:
        try:
            path = context.reports.build_daily_report()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"path": str(path)}

    @app.post("/api/reports/weekly")
    def weekly_report() -> dict[str, str]:
        try:
            path = context.reports.build_weekly_report()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"path": str(path)}

    @app.get("/api/reports/latest/{kind}")
    def latest_report(kind: str) -> dict[str, Any]:
        path = latest_report_path(context.settings.storage.report_output_dir, kind, datetime.now())
        if path is None:
            raise HTTPException(status_code=404, detail=f"Unknown report kind: {kind}")
        if not path.exists():
            return {"kind": kind, "exists": False, "path": str(path), "content": "", "updated_at": None}
        return {
            "kind": kind,
            "exists": True,
            "path": str(path),
            "content": path.read_text(encoding="utf-8"),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }

    @app.post("/api/test/llm")
    def test_llm() -> dict[str, Any]:
        ok, message = context.llm.test_connection()
        return {"ok": ok, "message": message}

    @app.post("/api/test/ocr")
    def test_ocr() -> dict[str, Any]:
        ok, message = context.ocr.test_connection()
        return {"ok": ok, "message": message}

    return app


def latest_report_path(output_dir: Path, kind: str, now: datetime) -> Path | None:
    if kind == "daily":
        return output_dir / f"{now.date().isoformat()}-daily.md"
    if kind == "weekly":
        start = now.date() - timedelta(days=now.date().weekday())
        end = start + timedelta(days=6)
        return output_dir / f"{start.isoformat()}_to_{end.isoformat()}-weekly.md"
    return None


def pop_review_item(context: AppContext, event_id_prefix: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    today = datetime.now().date()
    events = context.store.load_review(today)
    matches = [event for event in events if str(event.get("id", "")).startswith(event_id_prefix)]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No review event matches {event_id_prefix}")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail=f"Multiple review events match {event_id_prefix}")
    selected = matches[0]
    remaining = [event for event in events if event.get("id") != selected.get("id")]
    return selected, remaining
