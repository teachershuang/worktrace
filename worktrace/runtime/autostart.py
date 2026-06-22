from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


WINDOWS_STARTUP_SUBDIR = Path("Microsoft/Windows/Start Menu/Programs/Startup")


@dataclass(frozen=True)
class AutostartStatus:
    supported: bool
    enabled: bool
    startup_file: str | None
    launch_command: str | None
    mode: str
    reason: str | None = None


class AutostartManager:
    def __init__(self, config_path: Path, startup_dir: Path | None = None):
        self.config_path = config_path.resolve()
        self._startup_dir = startup_dir

    def status(self) -> AutostartStatus:
        if os.name != "nt":
            return AutostartStatus(
                supported=False,
                enabled=False,
                startup_file=None,
                launch_command=None,
                mode="tray",
                reason="autostart is currently supported on Windows only",
            )

        startup_file = self.startup_file()
        launch_command = self.launch_command()
        return AutostartStatus(
            supported=True,
            enabled=startup_file.exists(),
            startup_file=str(startup_file),
            launch_command=launch_command,
            mode="tray",
        )

    def enable(self) -> AutostartStatus:
        status = self.status()
        if not status.supported:
            return status

        startup_file = self.startup_file()
        startup_file.parent.mkdir(parents=True, exist_ok=True)
        startup_file.write_text(self.render_startup_script(), encoding="utf-8")
        return self.status()

    def disable(self) -> AutostartStatus:
        status = self.status()
        if not status.supported:
            return status

        startup_file = self.startup_file()
        startup_file.unlink(missing_ok=True)
        return self.status()

    def startup_dir(self) -> Path:
        if self._startup_dir is not None:
            return self._startup_dir
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / WINDOWS_STARTUP_SUBDIR

    def startup_file(self) -> Path:
        return self.startup_dir() / "WorkTrace.cmd"

    def launch_command(self) -> str:
        executable, args = resolve_launch_target(self.config_path)
        joined_args = " ".join(quote_windows_arg(arg) for arg in args)
        return f'{quote_windows_arg(executable)} {joined_args}'.strip()

    def render_startup_script(self) -> str:
        executable, args = resolve_launch_target(self.config_path)
        joined_args = " ".join(quote_windows_arg(arg) for arg in args)
        return "\n".join(
            [
                "@echo off",
                "setlocal",
                f'cd /d {quote_windows_arg(str(self.config_path.parent))}',
                f'start "" {quote_windows_arg(executable)} {joined_args}',
                "endlocal",
                "",
            ]
        )


def resolve_launch_target(config_path: Path) -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if executable.name.lower() == "worktrace-cli.exe":
            windowed = executable.with_name("WorkTrace.exe")
            if windowed.exists():
                executable = windowed
        return str(executable), ["tray", "--config", str(config_path)]

    python_executable = Path(sys.executable).resolve()
    pythonw = python_executable.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else python_executable
    project_root = Path(__file__).resolve().parents[2]
    return str(launcher), [str(project_root / "main.py"), "tray", "--config", str(config_path)]


def quote_windows_arg(value: str | Path) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch in text for ch in ' \t"&()[]{}^=;!+,`~'):
        return f'"{text}"'
    return text
