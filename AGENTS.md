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
- [x] Desktop, browser-console, and tray entry points automatically start the recorder loop while preserving an existing paused state.
- [x] Overlapping manual and scheduled recording cycles are rejected instead of producing duplicate events.
- [x] Configuration, runtime state, review rewrites, and reports use atomic replacement; invalid hot-reload settings keep the previous config intact.
- [x] The editable-config API masks the LLM API key and preserves it when the masked value is saved.
- [x] Empty bulk-review requests are rejected and cannot resolve the whole queue accidentally.

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
- [x] 2026-09-04 all 61 unit/integration tests, Python compileall, and both JavaScript syntax checks passed after the reliability review.
- [x] 2026-09-04 packaged `0.4.1` CLI reported the correct version and passed offline doctor with all bundled Windows dependencies available.
- [x] 2026-09-04 packaged `WorkTrace.exe` started one desktop process, exposed `/desktop-pet` with HTTP 200, and reported an automatically running recorder loop through `/api/status`.

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
- [x] Fixed high-confidence `is_work=false` responses being able to enter the effective timeline when the model returned contradictory JSON.
- [x] Fixed simultaneous scheduled and manual records producing duplicate captures and event writes.
- [x] Fixed invalid config hot reloads replacing the last working config and stale service failures remaining on the desktop pet.
- [x] Fixed generated reports and mutable local state being vulnerable to partial writes.
- [x] Fixed desktop and tray launches showing the UI without actually starting the background recorder.
- [x] Fixed empty bulk-review API requests selecting every pending event.

## Known Gaps

- [ ] `config.lan.example.yaml` intentionally contains a placeholder key; real LAN testing requires a private local config. Do not commit real keys.
- [ ] Computer Use can read the WebView accessibility tree, but screenshot capture and click injection remain unreliable for the transparent pywebview window on this machine; the native bridge and controls are present and unit tested.
- [ ] 2026-09-04 Computer Use GUI inspection could not run because the local plugin reported `Trusted RPC service is not configured`; packaged GUI verification used process/window metadata and the real local API instead.
- [ ] 2026-09-04 live OCR retest of `192.168.8.29:8866` timed out from the current workstation, so current-code LLM and full `record-once` LAN verification remain pending until the route is restored.
- [ ] Meeting state and media playback detection are not yet part of Windows foreground guards.
- [ ] Multi-monitor capture, region selection, and screenshot redaction are not implemented.
- [ ] Report editing exists in the console, but there is no rich native editor or versioned report history.
- [ ] Installer, signing, upgrade flow, and release channel are not implemented.

## Next Development Goal: v0.5.0 First-Run Readiness

The next single milestone is to make a new Windows user reach the first valid event without editing YAML or guessing service state.

- [ ] Show a first-run setup flow when OCR/LLM endpoints are still placeholders or have not passed validation.
- [ ] Validate OCR URL, protocol, LLM URL, API key, model, work periods, and storage paths before enabling automatic capture.
- [ ] Persist the last 100 OCR/LLM checks with latency, HTTP status, retry count, and user-facing failure category.
- [ ] Add bounded retries for transport errors, HTTP 429, and HTTP 5xx without retrying authentication or validation failures.
- [ ] Provide a one-click end-to-end test that captures once, runs OCR and classification, and clearly shows where the chain failed.
- [ ] Package and verify the flow in `WorkTrace.exe` with Computer Use and a real LAN service configuration.

After v0.5.0, continue with meeting/media foreground guards, native notifications, multi-monitor/redaction, report history, and the signed installer/update channel.
