from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from worktrace.capture.idle import get_idle_seconds
from worktrace.runtime.app_context import AppContext, build_app_context
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.runtime.time_windows import is_within_work_periods
from worktrace.timeline.merge import merge_events


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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return console_html()

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

    @app.post("/api/test/llm")
    def test_llm() -> dict[str, Any]:
        ok, message = context.llm.test_connection()
        return {"ok": ok, "message": message}

    @app.post("/api/test/ocr")
    def test_ocr() -> dict[str, Any]:
        ok, message = context.ocr.test_connection()
        return {"ok": ok, "message": message}

    return app


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


def console_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WorkTrace Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f3eb;
      --ink: #20231f;
      --muted: #687068;
      --line: #d8d2c3;
      --panel: #fffdf7;
      --accent: #1e6f5c;
      --accent-2: #c84b31;
      --ok: #227a4d;
      --warn: #a65f00;
      --bad: #b02a2a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(180deg, #f9f7f0 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      font-size: 14px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 253, 247, 0.86);
      position: sticky;
      top: 0;
      z-index: 2;
      backdrop-filter: blur(12px);
    }
    h1 { margin: 0; font-size: 22px; font-weight: 700; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; }
    button {
      min-height: 36px;
      padding: 0 12px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      cursor: pointer;
      border-radius: 6px;
      font: inherit;
    }
    button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    button.danger { color: var(--accent-2); }
    button:disabled { opacity: 0.56; cursor: not-allowed; }
    .grid {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 18px;
      align-items: start;
    }
    section {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }
    section h2 {
      margin: 0;
      padding: 12px 14px;
      font-size: 15px;
      border-bottom: 1px solid var(--line);
      background: #f3eee1;
    }
    .content { padding: 14px; }
    .status-row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 9px 0;
      border-bottom: 1px solid #ebe5d6;
    }
    .status-row:last-child { border-bottom: 0; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      background: #eee7d7;
      color: var(--muted);
      white-space: nowrap;
    }
    .pill.ok { background: #dceee3; color: var(--ok); }
    .pill.warn { background: #fff0cf; color: var(--warn); }
    .pill.bad { background: #f8dddd; color: var(--bad); }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 10px 9px;
      text-align: left;
      border-bottom: 1px solid #ebe5d6;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; background: #fbf8ef; }
    .actions { display: flex; gap: 6px; flex-wrap: wrap; }
    .log {
      min-height: 38px;
      padding: 10px 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      background: #fbf8ef;
    }
    @media (max-width: 880px) {
      header { align-items: flex-start; flex-direction: column; padding: 16px; }
      main { padding: 16px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>WorkTrace</h1>
      <div class="muted">本地日报生成助手控制台</div>
    </div>
    <div class="toolbar">
      <button class="primary" data-action="start">开始记录</button>
      <button data-action="pause">暂停</button>
      <button data-action="resume">恢复</button>
      <button data-action="record-once">立即记录</button>
      <button data-action="daily">生成日报</button>
      <button data-action="weekly">生成周报</button>
      <button class="danger" data-action="stop">停止</button>
    </div>
  </header>
  <main>
    <div class="grid">
      <section>
        <h2>运行状态</h2>
        <div class="content" id="status"></div>
        <div class="log" id="log">准备就绪</div>
      </section>
      <section>
        <h2>今日时间轴</h2>
        <div class="content">
          <table>
            <thead><tr><th>时间</th><th>项目</th><th>类别</th><th>事项</th></tr></thead>
            <tbody id="timeline"></tbody>
          </table>
        </div>
      </section>
      <section>
        <h2>待确认</h2>
        <div class="content">
          <table>
            <thead><tr><th>时间</th><th>事项</th><th>置信度</th><th>操作</th></tr></thead>
            <tbody id="review"></tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
  <script>
    const logEl = document.querySelector("#log");
    const statusEl = document.querySelector("#status");
    const timelineEl = document.querySelector("#timeline");
    const reviewEl = document.querySelector("#review");

    function setLog(text, failed = false) {
      logEl.textContent = text;
      logEl.style.color = failed ? "var(--bad)" : "var(--muted)";
    }

    async function request(path, options = {}) {
      const response = await fetch(path, { method: "GET", ...options });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || response.statusText);
      }
      return response.json();
    }

    function pill(text, mode) {
      return `<span class="pill ${mode || ""}">${text}</span>`;
    }

    async function refresh() {
      const [status, timeline, review] = await Promise.all([
        request("/api/status"),
        request("/api/timeline/today"),
        request("/api/review"),
      ]);
      statusEl.innerHTML = `
        <div class="status-row"><span>记录循环</span>${pill(status.loop_running ? "运行中" : "未运行", status.loop_running ? "ok" : "warn")}</div>
        <div class="status-row"><span>暂停状态</span>${pill(status.paused ? "已暂停" : "未暂停", status.paused ? "warn" : "ok")}</div>
        <div class="status-row"><span>工作时间</span>${pill(status.in_work_period ? "是" : "否", status.in_work_period ? "ok" : "warn")}</div>
        <div class="status-row"><span>OCR 连续失败</span>${pill(status.ocr_consecutive_failures, status.ocr_consecutive_failures ? "bad" : "ok")}</div>
        <div class="status-row"><span>系统空闲</span><span>${status.idle_seconds === null ? "未知" : Math.round(status.idle_seconds) + "s"}</span></div>
        <div class="status-row"><span>截图间隔</span><span>${status.screenshot_interval_seconds}s</span></div>
        <div class="status-row"><span>当前时间</span><span>${status.now.replace("T", " ")}</span></div>
      `;
      timelineEl.innerHTML = timeline.items.map(item => `
        <tr>
          <td>${item.start_at.slice(11, 16)}-${item.end_at.slice(11, 16)}</td>
          <td>${item.project || "-"}</td>
          <td>${item.category}</td>
          <td><strong>${item.title}</strong><div class="muted">${item.summary}</div></td>
        </tr>`).join("") || `<tr><td colspan="4" class="muted">暂无有效工作事件</td></tr>`;
      reviewEl.innerHTML = review.items.map(item => {
        const c = item.classification || {};
        const id = item.id || "";
        return `<tr>
          <td>${(item.captured_at || "").slice(11, 16)}</td>
          <td><strong>${c.title || "-"}</strong><div class="muted">${c.summary || ""}</div></td>
          <td>${c.confidence ?? "-"}</td>
          <td class="actions">
            <button data-review-work="${id}">工作</button>
            <button data-review-nonwork="${id}">非工作</button>
          </td>
        </tr>`;
      }).join("") || `<tr><td colspan="4" class="muted">暂无待确认事件</td></tr>`;
    }

    async function post(path, okText) {
      try {
        setLog("处理中...");
        await request(path, { method: "POST" });
        setLog(okText);
        await refresh();
      } catch (error) {
        setLog(error.message, true);
      }
    }

    document.addEventListener("click", event => {
      const action = event.target.dataset.action;
      const reviewWork = event.target.dataset.reviewWork;
      const reviewNonwork = event.target.dataset.reviewNonwork;
      if (action === "start") post("/api/start", "记录循环已启动");
      if (action === "pause") post("/api/pause", "记录已暂停");
      if (action === "resume") post("/api/resume", "记录已恢复");
      if (action === "stop") post("/api/stop", "停止请求已发送");
      if (action === "record-once") post("/api/record-once", "已完成一次记录");
      if (action === "daily") post("/api/reports/daily", "日报已生成");
      if (action === "weekly") post("/api/reports/weekly", "周报已生成");
      if (reviewWork) post(`/api/review/${reviewWork}/work`, "已标记为工作");
      if (reviewNonwork) post(`/api/review/${reviewNonwork}/nonwork`, "已标记为非工作");
    });

    refresh().catch(error => setLog(error.message, true));
    setInterval(() => refresh().catch(error => setLog(error.message, true)), 10000);
  </script>
</body>
</html>"""
