from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn

from worktrace.ui.api import create_app

logger = logging.getLogger(__name__)

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
        confirm_close=True,
    )

    def on_closed() -> None:
        server_handle.stop()

    def bootstrap(target_window) -> None:
        target_window.load_url(server_handle.url)

    window.events.closed += on_closed
    webview.start(bootstrap, window, debug=verbose)


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
