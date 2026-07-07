from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn
from PIL import Image, ImageDraw

from worktrace.ui.api import create_app
logger = logging.getLogger(__name__)
STATIC_ASSETS = Path(__file__).resolve().parent / "static" / "assets"

DESKTOP_WINDOW_WIDTH = 960
DESKTOP_WINDOW_HEIGHT = 680
DESKTOP_WINDOW_MIN_WIDTH = 720
DESKTOP_WINDOW_MIN_HEIGHT = 520


@dataclass
class LocalServerHandle:
    host: str
    port: int
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


class NativeWindowLifecycle:
    def __init__(self, window, server_handle: LocalServerHandle, pet_window=None):
        self.window = window
        self.server_handle = server_handle
        self.pet_window = pet_window
        self.exiting = False

    def hide_to_tray(self) -> bool:
        if self.exiting:
            return True
        logger.info("desktop window close requested; hiding to tray")
        self.window.hide()
        return False

    def show_window(self) -> None:
        self.window.show()
        self.window.restore()
        if self.pet_window is not None:
            self.pet_window.show()
            self.pet_window.restore()

    def exit_app(self) -> None:
        self.exiting = True
        if self.pet_window is not None:
            self.pet_window.destroy()
        self.window.destroy()

    def cleanup(self) -> None:
        if self.pet_window is not None:
            try:
                self.pet_window.destroy()
            except Exception:
                logger.debug("desktop pet window was already closed", exc_info=True)
        self.server_handle.stop()


def launch_native_window(
    config_path: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    verbose: bool = False,
) -> None:
    import webview

    server_handle = start_local_server(config_path, host=host, preferred_port=port, verbose=verbose)
    window = webview.create_window(
        "WorkTrace",
        html=loading_html(),
        width=DESKTOP_WINDOW_WIDTH,
        height=DESKTOP_WINDOW_HEIGHT,
        min_size=(DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_MIN_HEIGHT),
        background_color="#FFF8F2",
        text_select=True,
        confirm_close=False,
    )
    pet_window = webview.create_window(
        "WorkTrace Pet",
        html=native_pet_html(),
        width=176,
        height=176,
        x=32,
        y=180,
        resizable=False,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
        background_color="#00FF00",
        confirm_close=False,
    )
    lifecycle = NativeWindowLifecycle(window, server_handle, pet_window=pet_window)
    tray_icon = create_native_tray_icon(lifecycle)

    def on_closed() -> None:
        lifecycle.cleanup()

    def bootstrap(target_window) -> None:
        if tray_icon is not None:
            tray_icon.run_detached()
        target_window.load_url(server_handle.url)

    if tray_icon is not None:
        window.events.closing += lifecycle.hide_to_tray
    window.events.closed += on_closed
    try:
        webview.start(bootstrap, window, debug=verbose)
    finally:
        if tray_icon is not None:
            tray_icon.stop()

def create_native_tray_icon(lifecycle: NativeWindowLifecycle):
    try:
        import pystray
    except ImportError:
        logger.warning("pystray unavailable; desktop close-to-tray disabled")
        return None

    def show(icon, item) -> None:
        lifecycle.show_window()

    def open_console(icon, item) -> None:
        lifecycle.show_window()

    def exit_app(icon, item) -> None:
        lifecycle.exit_app()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("显示 WorkTrace", show, default=True),
        pystray.MenuItem("打开控制台", open_console),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", exit_app),
    )
    return pystray.Icon("WorkTrace", create_native_tray_image(), "WorkTrace", menu)


def create_native_tray_image() -> Image.Image:
    icon_path = STATIC_ASSETS / "icons" / "app-tray.png"
    if icon_path.exists():
        return Image.open(icon_path).convert("RGBA")

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(30, 111, 92, 255))
    draw.line((18, 24, 30, 38, 48, 18), fill=(255, 253, 247, 255), width=6, joint="curve")
    draw.line((18, 44, 46, 44), fill=(255, 253, 247, 230), width=4)
    return image


def start_local_server(
    config_path: Path,
    host: str = "127.0.0.1",
    preferred_port: int = 8765,
    verbose: bool = False,
) -> LocalServerHandle:
    port = choose_available_port(host, preferred_port)
    app = create_app(config_path, verbose=verbose)
    config = uvicorn.Config(app, host=host, port=port, log_level="info" if verbose else "warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="worktrace-native-api")
    thread.start()
    wait_for_server(host, port)
    return LocalServerHandle(host=host, port=port, server=server, thread=thread)


def choose_available_port(host: str, preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, preferred_port))
            return preferred_port
        except OSError:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])


def wait_for_server(host: str, port: int, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://{host}:{port}/api/status"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=1.0, trust_env=False) as client:
                response = client.get(url)
                response.raise_for_status()
                return
        except Exception as exc:  # pragma: no cover - exercised in runtime
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"desktop API server failed to start on {url}: {last_error}")


def loading_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WorkTrace</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #fffaf2;
      --ink: #251f19;
      --muted: #7b7267;
      --line: #eadbc8;
      --accent: #61b36d;
      --warm: #f5efe6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at 15% 10%, rgba(255, 228, 201, 0.9), transparent 26%),
        radial-gradient(circle at 88% 15%, rgba(216, 232, 220, 0.65), transparent 22%),
        linear-gradient(180deg, #fffdf9 0%, var(--bg) 100%);
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
    }
    .panel {
      width: min(520px, calc(100vw - 48px));
      padding: 28px 28px 24px;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: rgba(255, 253, 248, 0.92);
      box-shadow: 0 24px 70px rgba(76, 58, 36, 0.14);
      text-align: center;
    }
    .mark {
      width: 68px;
      height: 68px;
      margin: 0 auto 18px;
      border-radius: 20px;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, #2f2d2d 0%, #424040 100%);
      color: white;
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 0.03em;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.05;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }
    .bar {
      width: 100%;
      height: 10px;
      margin-top: 22px;
      border-radius: 999px;
      overflow: hidden;
      background: var(--warm);
      position: relative;
    }
    .bar::before {
      content: "";
      position: absolute;
      inset: 0;
      width: 35%;
      border-radius: 999px;
      background: linear-gradient(90deg, #63b270, #8bc39b);
      animation: move 1.2s ease-in-out infinite;
    }
    @keyframes move {
      0% { transform: translateX(-10%); }
      50% { transform: translateX(180%); }
      100% { transform: translateX(-10%); }
    }
  </style>
</head>
<body>
  <div class="panel">
    <div class="mark">W</div>
    <h1>WorkTrace</h1>
    <p>正在启动本地桌面控制台与后台服务</p>
    <div class="bar" aria-hidden="true"></div>
  </div>
</body>
</html>
""".strip()


def native_pet_html() -> str:
    mascot = (STATIC_ASSETS / "mascot" / "assistant-main.png").as_uri()
    cat = (STATIC_ASSETS / "mascot" / "cat.png").as_uri()
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WorkTrace Pet</title>
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: transparent;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      user-select: none;
    }}
    .pet {{
      width: 176px;
      height: 176px;
      display: grid;
      place-items: center;
      position: relative;
      -webkit-app-region: drag;
    }}
    .bubble {{
      position: absolute;
      left: 28px;
      bottom: 8px;
      min-width: 92px;
      padding: 7px 10px;
      border-radius: 999px;
      background: #dcf0df;
      color: #2d7a3d;
      border: 1px solid rgba(45, 122, 61, 0.16);
      box-shadow: 0 10px 28px rgba(61, 46, 31, 0.14);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
    }}
    .assistant {{
      width: 124px;
      height: 124px;
      object-fit: contain;
      image-rendering: auto;
      filter: drop-shadow(0 16px 22px rgba(65, 45, 24, 0.18));
      animation: float 2.8s ease-in-out infinite;
    }}
    .cat {{
      position: absolute;
      right: 14px;
      bottom: 26px;
      width: 48px;
      height: 48px;
      object-fit: contain;
      filter: drop-shadow(0 10px 14px rgba(65, 45, 24, 0.14));
    }}
    @keyframes float {{
      0%, 100% {{ transform: translateY(0); }}
      50% {{ transform: translateY(-5px); }}
    }}
  </style>
</head>
<body>
  <div class="pet" title="WorkTrace 桌宠">
    <img class="assistant" src="{mascot}" alt="WorkTrace 助手" />
    <img class="cat" src="{cat}" alt="助手猫咪" />
    <div class="bubble">待命中</div>
  </div>
</body>
</html>
""".strip()
