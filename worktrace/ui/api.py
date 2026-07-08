from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from worktrace import __version__
from worktrace.capture.idle import get_idle_seconds
from worktrace.config.settings import ConfigError
from worktrace.llm.client import LLMError
from worktrace.ocr.client import OCRError
from worktrace.runtime.autostart import AutostartManager
from worktrace.runtime.app_context import AppContext, build_app_context
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.runtime.time_windows import is_within_work_periods
from worktrace.timeline.merge import merge_events

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ConsoleRuntime:
    def __init__(self, context: AppContext):
        self.context = context
        self._loop_thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._lock = threading.Lock()
        self.service_checks: dict[str, dict[str, Any] | None] = {"ocr": None, "llm": None}

    def start_loop(self) -> bool:
        with self._lock:
            if self._loop_thread and self._loop_thread.is_alive():
                return False
            self._stop_event = threading.Event()
            loop = BackgroundRecorderLoop(
                self.context.settings,
                self.context.recorder,
                self.context.state_store,
                stop_event=self._stop_event,
            )
            self._loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
            self._loop_thread.start()
            return True

    def loop_running(self) -> bool:
        return bool(self._loop_thread and self._loop_thread.is_alive())

    def stop_loop(self, timeout: float = 3.0) -> bool:
        with self._lock:
            if not self._loop_thread or not self._loop_thread.is_alive():
                return True
            self.context.state_store.request_stop()
            if self._stop_event is not None:
                self._stop_event.set()
            thread = self._loop_thread
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def replace_context(self, context: AppContext) -> None:
        self.stop_loop(timeout=3.0)
        with self._lock:
            self.context = context

    def record_service_check(self, name: str, *, ok: bool, message: str, elapsed_ms: int) -> None:
        self.service_checks[name] = {
            "ok": ok,
            "message": message,
            "elapsed_ms": elapsed_ms,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }


def create_app(config_path: Path = Path("config.yaml"), verbose: bool = False) -> FastAPI:
    context = build_app_context(config_path, verbose=verbose)
    runtime = ConsoleRuntime(context)
    autostart = AutostartManager(config_path)
    app = FastAPI(title="WorkTrace Local Console", version=__version__)
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
            "last_activity": runtime_state_payload(state),
        }

    @app.get("/api/config/summary")
    def config_summary() -> dict[str, Any]:
        settings = context.settings
        autostart_status = autostart.status()
        return {
            "llm": {
                "base_url": settings.llm.base_url,
                "model": settings.llm.model,
                "timeout_seconds": settings.llm.timeout_seconds,
                "trust_env": settings.llm.trust_env,
            },
            "ocr": {
                "url": settings.ocr.url,
                "protocol": settings.ocr.protocol,
                "timeout_seconds": settings.ocr.timeout_seconds,
                "trust_env": settings.ocr.trust_env,
            },
            "recording": {
                "work_periods": settings.recording.work_periods,
                "screenshot_interval_seconds": settings.recording.screenshot_interval_seconds,
                "idle_skip_minutes": settings.recording.idle_skip_minutes,
                "enable_tray": settings.recording.enable_tray,
            },
            "storage": {
                "data_dir": str(settings.storage.data_dir),
                "report_output_dir": str(settings.storage.report_output_dir),
                "log_dir": str(settings.storage.log_dir),
            },
            "desktop": {
                "autostart_supported": autostart_status.supported,
                "autostart_enabled": autostart_status.enabled,
                "autostart_mode": autostart_status.mode,
                "autostart_path": autostart_status.startup_file,
                "autostart_reason": autostart_status.reason,
            },
        }

    @app.get("/api/config/editable")
    def config_editable() -> dict[str, Any]:
        settings = context.settings
        return {
            "config_path": str(config_path),
            "llm": {
                "base_url": settings.llm.base_url,
                "api_key": settings.llm.api_key,
                "model": settings.llm.model,
                "timeout_seconds": settings.llm.timeout_seconds,
                "trust_env": settings.llm.trust_env,
            },
            "ocr": {
                "url": settings.ocr.url,
                "protocol": settings.ocr.protocol,
                "timeout_seconds": settings.ocr.timeout_seconds,
                "trust_env": settings.ocr.trust_env,
            },
            "recording": {
                "work_periods": settings.recording.work_periods,
                "screenshot_interval_seconds": settings.recording.screenshot_interval_seconds,
                "idle_skip_minutes": settings.recording.idle_skip_minutes,
                "enable_tray": settings.recording.enable_tray,
            },
            "storage": {
                "data_dir": str(settings.storage.data_dir),
                "report_output_dir": str(settings.storage.report_output_dir),
                "log_dir": str(settings.storage.log_dir),
            },
            "restart_required": False,
        }

    @app.put("/api/config/editable")
    def config_save(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        nonlocal context
        config_payload = normalize_config_payload(payload)
        try:
            validated = context.settings.__class__.model_validate(config_payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"配置校验失败: {exc}") from exc

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(validated.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        try:
            next_context = build_app_context(config_path, verbose=verbose)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"配置已写入，但热更新失败，请重启 WorkTrace: {exc}") from exc
        runtime.replace_context(next_context)
        context = next_context
        return {
            "saved": True,
            "reloaded": True,
            "path": str(config_path),
            "restart_required": False,
            "message": "配置已保存，重启 WorkTrace 后生效。",
        }

    @app.get("/api/autostart")
    def autostart_status() -> dict[str, Any]:
        status = autostart.status()
        return status.__dict__

    @app.post("/api/autostart/enable")
    def autostart_enable() -> dict[str, Any]:
        return autostart.enable().__dict__

    @app.post("/api/autostart/disable")
    def autostart_disable() -> dict[str, Any]:
        return autostart.disable().__dict__

    @app.post("/api/start")
    def start() -> dict[str, Any]:
        context.state_store.resume()
        started = runtime.start_loop()
        return {"started": started, "loop_running": runtime.loop_running()}

    @app.post("/api/pause")
    def pause() -> dict[str, bool]:
        context.state_store.pause()
        return {"paused": True}

    @app.post("/api/resume")
    def resume() -> dict[str, Any]:
        context.state_store.resume()
        started = runtime.start_loop()
        return {"paused": False, "started": started, "loop_running": runtime.loop_running()}

    @app.post("/api/recording/start-or-resume")
    def recording_start_or_resume() -> dict[str, Any]:
        context.state_store.resume()
        started = runtime.start_loop()
        return {"paused": False, "started": started, "loop_running": runtime.loop_running()}

    @app.post("/api/recording/pause")
    def recording_pause() -> dict[str, Any]:
        context.state_store.pause()
        return {"paused": True, "loop_running": runtime.loop_running()}

    @app.post("/api/stop")
    def stop() -> dict[str, bool]:
        context.state_store.request_stop()
        return {"stop_requested": True}

    @app.post("/api/record-once")
    def record_once() -> dict[str, Any]:
        try:
            return context.recorder.record_once()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=describe_runtime_error(exc)) from exc

    @app.get("/api/timeline/today")
    def today_timeline(day: str | None = Query(default=None)) -> dict[str, Any]:
        target_day = parse_day(day)
        items = merge_events(context.store.load_effective(target_day))
        return {"date": target_day.isoformat(), "items": [item.to_dict() for item in items]}

    @app.get("/api/review")
    def review_list(day: str | None = Query(default=None)) -> dict[str, Any]:
        target_day = parse_day(day)
        return {"date": target_day.isoformat(), "items": context.store.load_review(target_day)}

    @app.post("/api/review/bulk/work")
    def review_bulk_work(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        payload = payload or {}
        ids = normalize_id_list(payload.get("ids"))
        target_day = parse_day(payload.get("date"))
        moved, remaining = split_review_items(context.store.load_review(target_day), ids)
        for event in moved:
            classification = dict(event.get("classification", {}))
            classification["should_record"] = True
            classification["is_work"] = True
            classification["need_review"] = False
            classification["skip_reason"] = None
            event["classification"] = classification
            context.store.append_effective(event, target_day)
        context.store.replace_review(target_day, remaining)
        return {"marked": "work", "count": len(moved), "date": target_day.isoformat()}

    @app.post("/api/review/bulk/nonwork")
    def review_bulk_nonwork(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        payload = payload or {}
        ids = normalize_id_list(payload.get("ids"))
        target_day = parse_day(payload.get("date"))
        moved, remaining = split_review_items(context.store.load_review(target_day), ids)
        context.store.replace_review(target_day, remaining)
        return {"marked": "nonwork", "count": len(moved), "date": target_day.isoformat()}

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
            raise HTTPException(status_code=500, detail=describe_runtime_error(exc)) from exc
        return {"path": str(path)}

    @app.post("/api/reports/weekly")
    def weekly_report() -> dict[str, str]:
        try:
            path = context.reports.build_weekly_report()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=describe_runtime_error(exc)) from exc
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

    @app.put("/api/reports/latest/{kind}")
    def save_latest_report(kind: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        path = latest_report_path(context.settings.storage.report_output_dir, kind, datetime.now())
        if path is None:
            raise HTTPException(status_code=404, detail=f"Unknown report kind: {kind}")
        content = payload.get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=422, detail="content must be a string")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "kind": kind,
            "saved": True,
            "path": str(path),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        }

    @app.get("/api/diagnostics")
    def diagnostics() -> dict[str, Any]:
        paths = {
            "data_dir": context.settings.storage.data_dir,
            "report_output_dir": context.settings.storage.report_output_dir,
            "log_dir": context.settings.storage.log_dir,
        }
        today = datetime.now().date()
        review_items = context.store.load_review(today)
        effective_items = context.store.load_effective(today)
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "ocr": {
                "url": context.settings.ocr.url,
                "protocol": context.settings.ocr.protocol,
                "consecutive_failures": context.recorder.consecutive_ocr_failures,
                "last_check": runtime.service_checks.get("ocr"),
            },
            "llm": {
                "base_url": context.settings.llm.base_url,
                "model": context.settings.llm.model,
                "last_check": runtime.service_checks.get("llm"),
            },
            "storage": [
                {
                    "name": name,
                    "path": str(path),
                    "exists": path.exists(),
                    "writable": is_writable_dir(path),
                }
                for name, path in paths.items()
            ],
            "events": {
                "effective_today": len(effective_items),
                "review_today": len(review_items),
                "raw_today": len(context.store.load_raw(today)),
            },
            "last_activity": runtime_state_payload(context.state_store.load()),
            "desktop": autostart.status().__dict__,
        }

    @app.post("/api/test/llm")
    def test_llm() -> dict[str, Any]:
        started_at = time.perf_counter()
        ok, message = context.llm.test_connection()
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        runtime.record_service_check("llm", ok=ok, message=message, elapsed_ms=elapsed_ms)
        if not ok:
            raise HTTPException(status_code=502, detail=describe_runtime_error(LLMError(message)))
        return {"ok": ok, "message": message, "elapsed_ms": elapsed_ms}

    @app.post("/api/test/ocr")
    def test_ocr() -> dict[str, Any]:
        started_at = time.perf_counter()
        ok, message = context.ocr.test_connection()
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        runtime.record_service_check("ocr", ok=ok, message=message, elapsed_ms=elapsed_ms)
        if not ok:
            raise HTTPException(status_code=502, detail=describe_runtime_error(OCRError(message)))
        return {"ok": ok, "message": message, "elapsed_ms": elapsed_ms}

    return app


def latest_report_path(output_dir: Path, kind: str, now: datetime) -> Path | None:
    if kind == "daily":
        return output_dir / f"{now.date().isoformat()}-daily.md"
    if kind == "weekly":
        start = now.date() - timedelta(days=now.date().weekday())
        end = start + timedelta(days=6)
        return output_dir / f"{start.isoformat()}_to_{end.isoformat()}-weekly.md"
    return None


def parse_day(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD") from exc


def normalize_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=422, detail="ids must be a string array")
    return value


def split_review_items(items: list[dict[str, Any]], ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not items:
        return [], []
    if not ids:
        return items, []

    selected: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for event in items:
        event_id = str(event.get("id", ""))
        if any(event_id.startswith(prefix) for prefix in ids):
            selected.append(event)
        else:
            remaining.append(event)
    return selected, remaining


def is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".worktrace-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


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


def runtime_state_payload(state) -> dict[str, Any]:
    return {
        "at": state.last_activity_at,
        "status": state.last_activity_status,
        "reason": state.last_activity_reason,
        "event_id": state.last_event_id,
    }


def normalize_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def section(name: str) -> dict[str, Any]:
        value = payload.get(name, {})
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail=f"{name} must be an object")
        return value

    llm = section("llm")
    ocr = section("ocr")
    recording = section("recording")
    storage = section("storage")
    work_periods_raw = recording.get("work_periods", [])
    if isinstance(work_periods_raw, str):
        work_periods = [item.strip() for item in work_periods_raw.replace("，", ",").split(",") if item.strip()]
    else:
        work_periods = work_periods_raw

    return {
        "llm": {
            "base_url": str(llm.get("base_url", "")).strip(),
            "api_key": str(llm.get("api_key", "")),
            "model": str(llm.get("model", "")).strip(),
            "timeout_seconds": float(llm.get("timeout_seconds", 60)),
            "trust_env": bool(llm.get("trust_env", False)),
        },
        "ocr": {
            "url": str(ocr.get("url", "")).strip(),
            "protocol": str(ocr.get("protocol", "multipart")).strip(),
            "timeout_seconds": float(ocr.get("timeout_seconds", 30)),
            "trust_env": bool(ocr.get("trust_env", False)),
        },
        "recording": {
            "work_periods": work_periods,
            "screenshot_interval_seconds": int(recording.get("screenshot_interval_seconds", 300)),
            "idle_skip_minutes": int(recording.get("idle_skip_minutes", 10)),
            "enable_tray": bool(recording.get("enable_tray", False)),
        },
        "storage": {
            "data_dir": str(storage.get("data_dir", "data")).strip(),
            "report_output_dir": str(storage.get("report_output_dir", "data/reports")).strip(),
            "log_dir": str(storage.get("log_dir", "logs")).strip(),
        },
    }


def describe_runtime_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()

    if isinstance(exc, ConfigError) or "config file not found" in lowered:
        return "未找到可用配置文件。请先复制并填写 config.yaml，再重新启动 WorkTrace。"

    if "no effective work events found for daily report" in lowered:
        return "今天还没有可用于生成日报的有效工作事件。请先记录一次，或在待确认列表中标记工作事件。"

    if "no effective work events or daily reports found for weekly report" in lowered:
        return "本周还没有可用于生成周报的日报或有效时间轴。请先记录工作事件并生成日报。"

    if isinstance(exc, LLMError) or "llm request failed" in lowered:
        if "401" in lowered or "unauthorized" in lowered:
            return "LLM 服务认证失败，请检查 llm.api_key 或模型网关的鉴权配置。"
        if "404" in lowered or "not found" in lowered:
            return "LLM 服务地址或模型名称不可用，请检查 llm.base_url 和 llm.model。"
        if "timed out" in lowered or "timeout" in lowered:
            return "LLM 服务请求超时，请检查模型负载、网络连通性或 timeout_seconds 配置。"
        return "LLM 服务调用失败，请检查模型服务状态和日志。"

    if isinstance(exc, OCRError) or "ocr request failed" in lowered or "ocr endpoint unreachable" in lowered:
        if "timed out" in lowered or "timeout" in lowered:
            return "OCR 服务请求超时，请检查 OCR 服务状态、网络连通性或 timeout_seconds 配置。"
        return "OCR 服务调用失败，请检查 OCR 地址、协议配置和服务状态。"

    return message or "操作失败，请查看日志。"
