const logEl = document.querySelector("#log");
const sideStatusEl = document.querySelector("#side-status");
const statusPillEl = document.querySelector("#state-pill");
const recordDotEl = document.querySelector("#record-dot");
const recordStateEl = document.querySelector("#record-state");
const recordCopyEl = document.querySelector("#record-copy");
const todayDateEl = document.querySelector("#today-date");
const idleTimeEl = document.querySelector("#idle-time");
const intervalEl = document.querySelector("#interval");
const metricDurationEl = document.querySelector("#metric-duration");
const metricEventsEl = document.querySelector("#metric-events");
const metricReviewEl = document.querySelector("#metric-review");
const metricOcrEl = document.querySelector("#metric-ocr");
const timelineListEl = document.querySelector("#timeline-list");
const reviewListEl = document.querySelector("#review-list");
const reportPreviewEl = document.querySelector("#report-preview");
const settingsGridEl = document.querySelector("#settings-grid");

function setLog(text, failed = false) {
  logEl.textContent = text;
  logEl.style.color = failed ? "var(--red)" : "var(--muted)";
}

async function request(path, options = {}) {
  const response = await fetch(path, { method: "GET", ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function humanizeError(message) {
  if (!message) return "操作失败，请查看日志。";
  if (message.includes("no effective work events found for daily report")) {
    return "今天还没有有效工作事件。请先记录一次，或在待确认中标记工作事件后再生成日报。";
  }
  if (message.includes("no effective work events or daily reports found for weekly report")) {
    return "本周还没有可用于周报的日报或有效时间轴。请先记录工作事件并生成日报。";
  }
  return message;
}

function formatDuration(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours}h ${String(rest).padStart(2, "0")}m`;
}

function timelineMinutes(items) {
  return items.reduce((total, item) => {
    const start = new Date(item.start_at).getTime();
    const end = new Date(item.end_at).getTime();
    const minutes = Math.max(Math.round((end - start) / 60000), 5);
    return total + minutes;
  }, 0);
}

function setPill(element, text, mode) {
  element.className = `pill ${mode || "muted"}`;
  element.textContent = text;
}

async function refresh() {
  const [status, timeline, review] = await Promise.all([
    request("/api/status"),
    request("/api/timeline/today"),
    request("/api/review"),
  ]);

  const now = new Date(status.now);
  todayDateEl.textContent = now.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "long",
  });

  const runningText = status.loop_running ? "记录中" : "未运行";
  const stateMode = status.paused ? "warn" : status.loop_running ? "ok" : "muted";
  setPill(statusPillEl, status.paused ? "已暂停" : runningText, stateMode);
  sideStatusEl.textContent = status.paused ? "暂停中" : runningText;
  recordStateEl.textContent = status.paused ? "暂停中" : runningText;
  recordCopyEl.textContent = status.in_work_period ? "处于配置的工作时间段" : "当前不在工作时间段";
  recordDotEl.style.background = status.loop_running && !status.paused ? "var(--green)" : "var(--amber)";

  idleTimeEl.textContent = status.idle_seconds === null ? "未知" : `${Math.round(status.idle_seconds)}s`;
  intervalEl.textContent = `${status.screenshot_interval_seconds}s`;
  metricDurationEl.textContent = formatDuration(timelineMinutes(timeline.items));
  metricEventsEl.textContent = timeline.items.length;
  metricReviewEl.textContent = review.items.length;
  metricOcrEl.textContent = status.ocr_consecutive_failures ? `${status.ocr_consecutive_failures} 次失败` : "正常";

  timelineListEl.innerHTML = timeline.items.slice(-8).reverse().map(item => `
    <li class="event-item">
      <span class="event-time">${item.start_at.slice(11, 16)}</span>
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <span class="muted">${escapeHtml(item.summary || "")}</span>
      </div>
    </li>
  `).join("") || `<li class="muted">暂无有效工作事件</li>`;

  reviewListEl.innerHTML = review.items.map(item => {
    const c = item.classification || {};
    const id = item.id || "";
    return `
      <div class="review-row">
        <span class="event-time">${(item.captured_at || "").slice(11, 16)}</span>
        <div>
          <strong>${escapeHtml(c.title || "-")}</strong>
          <div class="muted">${escapeHtml(c.summary || "")}</div>
        </div>
        <span>${c.confidence ?? "-"}</span>
        <div class="review-actions">
          <button class="quick-button" data-review-work="${id}">工作</button>
          <button class="quick-button danger" data-review-nonwork="${id}">非工作</button>
        </div>
      </div>
    `;
  }).join("") || `<div class="muted">暂无待确认事件</div>`;
}

function renderSettingItem(label, value) {
  return `
    <div class="setting-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

async function refreshSettings() {
  const config = await request("/api/config/summary");
  settingsGridEl.innerHTML = [
    renderSettingItem("大模型地址", config.llm.base_url),
    renderSettingItem("大模型名称", config.llm.model),
    renderSettingItem("OCR 地址", config.ocr.url),
    renderSettingItem("OCR 协议", config.ocr.protocol),
    renderSettingItem("工作时段", config.recording.work_periods.join("、")),
    renderSettingItem("截图间隔", `${config.recording.screenshot_interval_seconds}s`),
    renderSettingItem("空闲跳过", `${config.recording.idle_skip_minutes} 分钟`),
    renderSettingItem("数据目录", config.storage.data_dir),
    renderSettingItem("报告目录", config.storage.report_output_dir),
    renderSettingItem("日志目录", config.storage.log_dir),
  ].join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function post(path, okText, button = null) {
  try {
    if (button) {
      button.disabled = true;
      button.dataset.busy = "true";
    }
    setLog("处理中...");
    const result = await request(path, { method: "POST" });
    setLog(result.path ? `${okText}: ${result.path}` : okText);
    await refresh();
    if (path.startsWith("/api/reports/")) {
      await refreshReports();
    }
  } catch (error) {
    setLog(humanizeError(error.message), true);
  } finally {
    if (button) {
      button.disabled = false;
      delete button.dataset.busy;
    }
  }
}

function renderReportBlock(label, report) {
  if (!report.exists) {
    return `## ${label}\n暂无已生成报告`;
  }
  return `## ${label}\n路径：${report.path}\n更新时间：${report.updated_at || "-"}\n\n${report.content}`;
}

async function refreshReports() {
  try {
    const [daily, weekly] = await Promise.all([
      request("/api/reports/latest/daily"),
      request("/api/reports/latest/weekly"),
    ]);
    reportPreviewEl.textContent = [
      renderReportBlock("今日日报", daily),
      renderReportBlock("本周周报", weekly),
    ].join("\n\n---\n\n");
  } catch (error) {
    reportPreviewEl.textContent = `报告读取失败：${error.message}`;
  }
}

document.addEventListener("click", event => {
  const target = event.target.closest("button");
  if (!target) return;
  const action = target.dataset.action;
  const reviewWork = target.dataset.reviewWork;
  const reviewNonwork = target.dataset.reviewNonwork;
  if (target.dataset.refresh !== undefined) refresh();
  if (action === "start") post("/api/start", "记录循环已启动", target);
  if (action === "pause") post("/api/pause", "记录已暂停", target);
  if (action === "resume") post("/api/resume", "记录已恢复", target);
  if (action === "stop") post("/api/stop", "停止请求已发送", target);
  if (action === "record-once") post("/api/record-once", "已完成一次记录", target);
  if (action === "daily") post("/api/reports/daily", "日报已生成", target);
  if (action === "weekly") post("/api/reports/weekly", "周报已生成", target);
  if (action === "refresh-reports") refreshReports().then(() => setLog("报告预览已刷新"));
  if (action === "test-ocr") post("/api/test/ocr", "OCR 测试完成", target);
  if (action === "test-llm") post("/api/test/llm", "LLM 测试完成", target);
  if (reviewWork) post(`/api/review/${reviewWork}/work`, "已标记为工作", target);
  if (reviewNonwork) post(`/api/review/${reviewNonwork}/nonwork`, "已标记为非工作", target);
});

refresh().catch(error => setLog(error.message, true));
refreshSettings().catch(error => setLog(humanizeError(error.message), true));
refreshReports().catch(error => {
  reportPreviewEl.textContent = `报告读取失败：${humanizeError(error.message)}`;
});
setInterval(() => refresh().catch(error => setLog(error.message, true)), 10000);
