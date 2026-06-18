from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from worktrace.config.logging import setup_logging
from worktrace.config.settings import ConfigError, load_config
from worktrace.llm.client import LLMClient
from worktrace.ocr.client import OCRClient


app = typer.Typer(help="WorkTrace local daily report assistant.")
console = Console()


def load_settings_or_exit(config: Path, verbose: bool = False):
    try:
        settings = load_config(config)
        setup_logging(settings.storage.log_dir, verbose=verbose)
        return settings
    except ConfigError as exc:
        console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("config-show")
def config_show(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Load and print the effective configuration summary."""
    settings = load_settings_or_exit(config, verbose=verbose)
    table = Table(title="WorkTrace Configuration")
    table.add_column("Section")
    table.add_column("Key")
    table.add_column("Value")

    table.add_row("llm", "base_url", settings.llm.base_url)
    table.add_row("llm", "model", settings.llm.model)
    table.add_row("llm", "timeout_seconds", str(settings.llm.timeout_seconds))
    table.add_row("ocr", "url", settings.ocr.url)
    table.add_row("ocr", "timeout_seconds", str(settings.ocr.timeout_seconds))
    table.add_row("recording", "work_periods", ", ".join(settings.recording.work_periods))
    table.add_row("recording", "screenshot_interval_seconds", str(settings.recording.screenshot_interval_seconds))
    table.add_row("recording", "idle_skip_minutes", str(settings.recording.idle_skip_minutes))
    table.add_row("recording", "enable_tray", str(settings.recording.enable_tray))
    table.add_row("storage", "data_dir", str(settings.storage.data_dir))
    table.add_row("storage", "report_output_dir", str(settings.storage.report_output_dir))
    table.add_row("storage", "log_dir", str(settings.storage.log_dir))
    console.print(table)


@app.command("config-json")
def config_json(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
) -> None:
    """Print validated config as JSON."""
    settings = load_settings_or_exit(config)
    console.print(json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("test-llm")
def test_llm(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Test OpenAI-compatible LLM connectivity."""
    settings = load_settings_or_exit(config, verbose=verbose)
    ok, message = LLMClient(settings.llm).test_connection()
    if ok:
        console.print(f"[green]LLM OK:[/green] {message}")
        return
    console.print(f"[red]LLM failed:[/red] {message}")
    raise typer.Exit(code=1)


@app.command("test-ocr")
def test_ocr(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Test OCR endpoint reachability."""
    settings = load_settings_or_exit(config, verbose=verbose)
    ok, message = OCRClient(settings.ocr).test_connection()
    if ok:
        console.print(f"[green]OCR OK:[/green] {message}")
        return
    console.print(f"[red]OCR failed:[/red] {message}")
    raise typer.Exit(code=1)
