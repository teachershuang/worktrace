# WorkTrace Agent Notes

## Project Structure

```text
worktrace/
  capture/        Screen capture, active-window metadata, idle detection
  classifier/     LLM-based screen activity classification
  config/         YAML config loading, validation, logging setup
  llm/            OpenAI-compatible LLM client
  ocr/            HTTP OCR client
  report/         Daily and weekly report generation
  runtime/        App context, recorder, background loop, runtime state, autostart
  timeline/       JSONL event store and timeline merge
  ui/             CLI, FastAPI console, native desktop window, tray, desktop pet
  ui/static/      Local console HTML/CSS/JS and mascot assets
prompts/          LLM prompts for classification, merge, daily report, weekly report
tests/            Unit and integration tests
scripts/          Windows build script
docs/images/      README screenshots
dist/             Local PyInstaller output, not a source artifact
tmp/              Local test data and temporary configs, not committed
data/             Runtime event/report state, not committed
```

## Current Product Status

- [x] Windows local desktop app can be packaged as `WorkTrace.exe`.
- [x] Native desktop window starts as a small app window, not full screen.
- [x] Local FastAPI console runs inside the desktop window.
- [x] CLI can test OCR, test LLM, record once, show timeline, generate daily report, and generate weekly report.
- [x] Screen capture works on Windows primary monitor.
- [x] Active window app name and title are captured.
- [x] OCR HTTP service integration works with the LAN PaddleOCR endpoint.
- [x] OpenAI-compatible LLM integration works when configured with the LiteLLM master key.
- [x] Content-level work recognition works with OCR text, app/window metadata, recent context, and project list.
- [x] High-confidence work events are written to the effective timeline.
- [x] Low-confidence events go to the review queue.
- [x] Non-work or skipped events are excluded from the effective timeline.
- [x] Daily and weekly Markdown reports are generated from real timeline data.
- [x] Runtime status shows latest recorded/review/skipped/failed activity in console and desktop pet panel.
- [x] Desktop tray mode, desktop pet, autostart, and close-to-tray behavior exist.
- [x] PyInstaller build was run and the packaged CLI was tested against real OCR/LLM services.
- [x] Windows foreground guards skip capture while locked, while WorkTrace is foreground, or for configured full-screen apps.
- [x] Paused/out-of-work/idle polling interval is configurable and defaults to 5 seconds.
- [x] Runtime state and event files use in-process locks and atomic replacement for rewrite operations.
- [x] Chinese timeline similarity uses character bigrams instead of treating a whole sentence as one token.
- [x] Windows package excludes unrelated Qt, NumPy, MKL, SSH, and notebook dependencies.
- [x] Native desktop pet loads mascot images from the same local FastAPI origin so packaged WebView2 windows do not depend on `file:///` asset access.
- [x] Native desktop pet polls the local runtime and shows recording, paused, pending review, waiting, standby, and service error states.
- [x] Clicking the native desktop pet opens a compact action panel for start/resume, pause, record once, daily report, and opening the full console.

## Real Test Record

- [x] `python main.py test-ocr --config tmp\real_test\config.yaml` passed against `http://192.168.8.29:8866/ocr`.
- [x] `python main.py test-llm --config tmp\real_test\config.yaml` passed against `http://192.168.8.29:4000/v1`.
- [x] `python main.py doctor --config tmp\real_test\config.yaml` passed with OCR and LLM checks enabled.
- [x] Multiple `record-once` runs produced real OCR + LLM classifications and effective timeline entries.
- [x] Daily report generation completed from real recorded events.
- [x] Weekly report generation completed from real recorded events.
- [x] `dist\WorkTrace\WorkTrace-cli.exe doctor --config dist\WorkTrace\config.yaml` passed with OCR and LLM checks enabled.
- [x] `dist\WorkTrace\WorkTrace-cli.exe record-once --config dist\WorkTrace\config.yaml` recorded a real high-confidence work event.
- [x] `WorkTrace.exe` desktop window was launched and inspected with Computer Use before the user interrupted the last verification pass.
- [x] 2026-07-14 packaged `WorkTrace.exe` exposed both `WorkTrace` and `WorkTrace Pet` windows to Computer Use.
- [x] 2026-07-14 packaged API start, pause, immediate stop, and config hot-reload loop restart all passed.
- [x] 2026-07-14 packaged CLI offline doctor passed after the Windows bundle was reduced from 747.44 MB to 82.88 MB.
- [x] 2026-07-14 rebuilt desktop pet exposed `WorkTrace 助手`, `助手猫咪`, and `待命中` in the packaged WebView accessibility tree.
- [x] 2026-07-15 packaged `0.4.0` desktop pet exposed its action controls to Computer Use and tracked `standby`, `recording`, `paused`, `review`, and `error` runtime states.
- [x] 2026-07-15 packaged API state transitions passed for start/resume, pause, pending review count, and OCR service alert.

## Findings Fixed During Review

- [x] Fixed recursive context growth: previous effective event used to include its full saved `context`, which recursively embedded older events and eventually caused LiteLLM `400 Bad Request` because the request exceeded model context size.
- [x] Added `compact_event_for_context()` so only a small previous-event summary is sent to the LLM.
- [x] Added regression coverage to ensure OCR payloads and recursive context are not reinserted into the next LLM prompt.
- [x] Fixed delayed stop: API and tray now signal the loop event instead of waiting for the screenshot interval.
- [x] Fixed config hot reload silently stopping an active recorder loop.
- [x] Fixed single review actions writing historical events into today's files.
- [x] Fixed concurrent state/review writes and malformed JSONL lines breaking the local timeline.
- [x] Fixed invalid OCR JSON bypassing the metadata-only fallback path.
- [x] Fixed Chinese rule-based timeline similarity returning zero for related non-identical sentences.
- [x] Fixed packaged native desktop pet opening an empty transparent WebView because local `file:///` mascot images were not reliably loaded.
- [x] Fixed pywebview recursively scanning native window objects by keeping bridge references private.

## Known Gaps

- [ ] `config.lan.example.yaml` still contains a rejected LLM key for LiteLLM; real testing required a temporary local config using the actual LiteLLM master key. Do not commit real keys.
- [ ] Computer Use can read the WebView accessibility tree, but screenshot capture and click injection remain unreliable for the transparent pywebview window on this machine; the native bridge and controls are present and unit tested.
- [ ] The current workstation is on `172.16.16.0/24`; 2026-07-14 live retest of `192.168.8.29` OCR/LLM/SSH timed out until the LAN route is restored.
- [ ] Meeting state and media playback detection are not yet part of Windows foreground guards.
- [ ] Multi-monitor capture, region selection, and screenshot redaction are not implemented.
- [ ] Report editing exists in the console, but there is no rich native editor or versioned report history.
- [ ] Installer, signing, upgrade flow, and release channel are not implemented.

## Next Development Plan

1. Add an installer and first-run setup wizard for OCR/LLM endpoints, API key, work periods, and optional autostart.
2. Persist service diagnostics history with OCR/LLM latency, HTTP status, retry count, and recent failures.
3. Extend Windows foreground guards with meeting state and media playback rules.
4. Add native desktop notifications for review queue and repeated service failures.
5. Add multi-monitor capture, region selection, and screenshot redaction.
6. Add a rich report editor with local version history.
