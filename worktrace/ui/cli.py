from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from worktrace.config.logging import setup_logging
from worktrace.config.settings import ConfigError, load_config
from worktrace.capture.screen import ScreenCapture
from worktrace.classifier.activity import ActivityClassifier
from worktrace.llm.client import LLMClient
from worktrace.ocr.client import OCRClient
from worktrace.report.generator import ReportGenerator
from worktrace.runtime.loop import BackgroundRecorderLoop
from worktrace.runtime.recorder import WorkRecorder
from worktrace.runtime.state import RuntimeStateStore
from worktrace.timeline.merge import merge_events
from worktrace.timeline.store import EventStore


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


def build_recorder(config: Path, verbose: bool = False) -> WorkRecorder:
    settings = load_settings_or_exit(config, verbose=verbose)
    llm = LLMClient(settings.llm)
    return WorkRecorder(
        capture=ScreenCapture(),
        ocr=OCRClient(settings.ocr),
        classifier=ActivityClassifier(llm),
        store=EventStore(settings.storage.data_dir),
    )


def build_state_store(settings) -> RuntimeStateStore:
    return RuntimeStateStore(settings.storage.data_dir / "runtime_state.json")


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


@app.command("record-once")
def record_once(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Capture, OCR, classify, and store one event."""
    recorder = build_recorder(config, verbose=verbose)
    try:
        event = recorder.record_once()
    except Exception as exc:
        console.print(f"[red]record-once failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    classification = event["classification"]
    console.print(
        f"[green]Recorded:[/green] {classification['title']} "
        f"(record={classification['should_record']}, review={classification['need_review']}, "
        f"confidence={classification['confidence']})"
    )


@app.command("today-timeline")
def today_timeline(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Show today's effective raw events."""
    from datetime import datetime

    settings = load_settings_or_exit(config, verbose=verbose)
    store = EventStore(settings.storage.data_dir)
    items = merge_events(store.load_effective(datetime.now().date()))
    table = Table(title="Today's Timeline")
    table.add_column("Period")
    table.add_column("Project")
    table.add_column("Category")
    table.add_column("Title")
    table.add_column("Summary")
    for item in items:
        table.add_row(
            f"{item.start_at:%H:%M}-{item.end_at:%H:%M}",
            str(item.project or "-"),
            item.category,
            item.title,
            item.summary,
        )
    console.print(table)


@app.command("review-list")
def review_list(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Show today's events that need review."""
    from datetime import datetime

    settings = load_settings_or_exit(config, verbose=verbose)
    store = EventStore(settings.storage.data_dir)
    events = store.load_review(datetime.now().date())
    table = Table(title="Review Queue")
    table.add_column("ID")
    table.add_column("Time")
    table.add_column("Title")
    table.add_column("Summary")
    table.add_column("Confidence")
    for event in events:
        classification = event.get("classification", {})
        table.add_row(
            str(event.get("id", ""))[:10],
            str(event.get("captured_at", ""))[11:16],
            str(classification.get("title") or "-"),
            str(classification.get("summary") or "-"),
            str(classification.get("confidence") or "-"),
        )
    console.print(table)


@app.command("review-mark-work")
def review_mark_work(
    event_id_prefix: str = typer.Argument(..., help="ID or ID prefix from review-list."),
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Mark a review item as work and add it to effective timeline."""
    from datetime import datetime

    settings = load_settings_or_exit(config, verbose=verbose)
    store = EventStore(settings.storage.data_dir)
    day = datetime.now().date()
    event, remaining = pop_review_item(store, day, event_id_prefix)
    classification = dict(event.get("classification", {}))
    classification["should_record"] = True
    classification["is_work"] = True
    classification["need_review"] = False
    classification["skip_reason"] = None
    event["classification"] = classification
    store.replace_review(day, remaining)
    store.append_effective(event, day)
    console.print(f"[green]Marked as work:[/green] {event.get('id')}")


@app.command("review-mark-nonwork")
def review_mark_nonwork(
    event_id_prefix: str = typer.Argument(..., help="ID or ID prefix from review-list."),
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Mark a review item as non-work and remove it from review queue."""
    from datetime import datetime

    settings = load_settings_or_exit(config, verbose=verbose)
    store = EventStore(settings.storage.data_dir)
    day = datetime.now().date()
    event, remaining = pop_review_item(store, day, event_id_prefix)
    store.replace_review(day, remaining)
    console.print(f"[yellow]Marked as non-work:[/yellow] {event.get('id')}")


@app.command("daily-report")
def daily_report(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Generate today's daily report."""
    settings = load_settings_or_exit(config, verbose=verbose)
    generator = ReportGenerator(
        llm=LLMClient(settings.llm),
        store=EventStore(settings.storage.data_dir),
        output_dir=settings.storage.report_output_dir,
    )
    try:
        path = generator.build_daily_report()
    except Exception as exc:
        console.print(f"[red]daily report failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Daily report written:[/green] {path}")


@app.command("weekly-report")
def weekly_report(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Generate this week's weekly report."""
    settings = load_settings_or_exit(config, verbose=verbose)
    generator = ReportGenerator(
        llm=LLMClient(settings.llm),
        store=EventStore(settings.storage.data_dir),
        output_dir=settings.storage.report_output_dir,
    )
    try:
        path = generator.build_weekly_report()
    except Exception as exc:
        console.print(f"[red]weekly report failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Weekly report written:[/green] {path}")


@app.command("start")
def start_recording(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Start the foreground background recording loop."""
    settings = load_settings_or_exit(config, verbose=verbose)
    llm = LLMClient(settings.llm)
    recorder = WorkRecorder(
        capture=ScreenCapture(),
        ocr=OCRClient(settings.ocr),
        classifier=ActivityClassifier(llm),
        store=EventStore(settings.storage.data_dir),
    )
    console.print("[green]WorkTrace recording loop started.[/green] Press Ctrl+C to exit.")
    try:
        BackgroundRecorderLoop(settings, recorder, build_state_store(settings)).run_forever()
    except KeyboardInterrupt:
        console.print("[yellow]Recording loop exited.[/yellow]")


@app.command("pause")
def pause_recording(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
) -> None:
    """Pause the background recording loop."""
    settings = load_settings_or_exit(config)
    build_state_store(settings).pause()
    console.print("[yellow]Recording paused.[/yellow]")


@app.command("resume")
def resume_recording(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
) -> None:
    """Resume the background recording loop."""
    settings = load_settings_or_exit(config)
    build_state_store(settings).resume()
    console.print("[green]Recording resumed.[/green]")


@app.command("stop")
def stop_recording(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config YAML."),
) -> None:
    """Ask the foreground recording loop to stop."""
    settings = load_settings_or_exit(config)
    build_state_store(settings).request_stop()
    console.print("[yellow]Stop requested.[/yellow]")


def pop_review_item(store: EventStore, day, event_id_prefix: str):
    events = store.load_review(day)
    matches = [event for event in events if str(event.get("id", "")).startswith(event_id_prefix)]
    if not matches:
        console.print(f"[red]No review event matches:[/red] {event_id_prefix}")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        console.print(f"[red]Multiple review events match:[/red] {event_id_prefix}")
        raise typer.Exit(code=1)
    selected = matches[0]
    remaining = [event for event in events if event.get("id") != selected.get("id")]
    return selected, remaining
