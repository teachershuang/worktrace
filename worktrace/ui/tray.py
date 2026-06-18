from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

import uvicorn
from PIL import Image, ImageDraw

from worktrace.runtime.app_context import AppContext, build_app_context
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.ui.api import create_app

logger = logging.getLogger(__name__)


class TrayRuntime:
    def __init__(self, config_path: Path, host: str, port: int, verbose: bool = False):
        self.config_path = config_path
        self.host = host
        self.port = port
        self.context: AppContext = build_app_context(config_path, verbose=verbose)
        self._record_thread: threading.Thread | None = None
        self._console_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def console_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start_recording(self) -> None:
        with self._lock:
            if self._record_thread and self._record_thread.is_alive():
                return
            loop = BackgroundRecorderLoop(self.context.settings, self.context.recorder, self.context.state_store)
            self._record_thread = threading.Thread(target=loop.run_forever, daemon=True, name="worktrace-recorder")
            self._record_thread.start()

    def pause(self) -> None:
        self.context.state_store.pause()

    def resume(self) -> None:
        self.context.state_store.resume()

    def record_once(self) -> None:
        self._run_async(self.context.recorder.record_once, "record-once")

    def generate_daily_report(self) -> None:
        self._run_async(self.context.reports.build_daily_report, "daily-report")

    def start_console(self) -> None:
        with self._lock:
            if self._console_thread and self._console_thread.is_alive():
                return

            def run() -> None:
                app = create_app(self.config_path)
                uvicorn.run(app, host=self.host, port=self.port, log_level="warning")

            self._console_thread = threading.Thread(target=run, daemon=True, name="worktrace-console")
            self._console_thread.start()

    def open_console(self) -> None:
        self.start_console()
        webbrowser.open(self.console_url)

    def shutdown(self) -> None:
        self.context.state_store.request_stop()

    @staticmethod
    def _run_async(func, name: str) -> None:
        def run() -> None:
            try:
                func()
            except Exception:
                logger.exception("tray action failed: %s", name)

        threading.Thread(target=run, daemon=True, name=f"worktrace-{name}").start()


def run_tray(config_path: Path = Path("config.yaml"), host: str = "127.0.0.1", port: int = 8765, verbose: bool = False) -> None:
    import pystray

    runtime = TrayRuntime(config_path=config_path, host=host, port=port, verbose=verbose)

    def action_start(icon, item) -> None:
        runtime.start_recording()

    def action_pause(icon, item) -> None:
        runtime.pause()

    def action_resume(icon, item) -> None:
        runtime.resume()

    def action_record_once(icon, item) -> None:
        runtime.record_once()

    def action_daily(icon, item) -> None:
        runtime.generate_daily_report()

    def action_console(icon, item) -> None:
        runtime.open_console()

    def action_quit(icon, item) -> None:
        runtime.shutdown()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("开始记录", action_start),
        pystray.MenuItem("暂停记录", action_pause),
        pystray.MenuItem("恢复记录", action_resume),
        pystray.MenuItem("立即记录一次", action_record_once),
        pystray.MenuItem("生成日报", action_daily),
        pystray.MenuItem("打开控制台", action_console),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", action_quit),
    )
    icon = pystray.Icon("WorkTrace", create_tray_icon(), "WorkTrace", menu)
    icon.run()


def create_tray_icon() -> Image.Image:
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(30, 111, 92, 255))
    draw.line((18, 24, 30, 38, 48, 18), fill=(255, 253, 247, 255), width=6, joint="curve")
    draw.line((18, 44, 46, 44), fill=(255, 253, 247, 230), width=4)
    return image
