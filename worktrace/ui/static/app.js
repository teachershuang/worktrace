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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function post(path, okText) {
  try {
    setLog("处理中...");
    const result = await request(path, { method: "POST" });
    setLog(result.path ? `${okText}: ${result.path}` : okText);
    await refresh();
  } catch (error) {
    setLog(error.message, true);
  }
}

document.addEventListener("click", event => {
  const target = event.target.closest("button");
  if (!target) return;
  const action = target.dataset.action;
  const reviewWork = target.dataset.reviewWork;
  const reviewNonwork = target.dataset.reviewNonwork;
  if (target.dataset.refresh !== undefined) refresh();
  if (action === "start") post("/api/start", "记录循环已启动");
  if (action === "pause") post("/api/pause", "记录已暂停");
  if (action === "resume") post("/api/resume", "记录已恢复");
  if (action === "stop") post("/api/stop", "停止请求已发送");
  if (action === "record-once") post("/api/record-once", "已完成一次记录");
  if (action === "daily") post("/api/reports/daily", "日报已生成");
  if (action === "weekly") post("/api/reports/weekly", "周报已生成");
  if (action === "test-ocr") post("/api/test/ocr", "OCR 测试完成");
  if (action === "test-llm") post("/api/test/llm", "LLM 测试完成");
  if (reviewWork) post(`/api/review/${reviewWork}/work`, "已标记为工作");
  if (reviewNonwork) post(`/api/review/${reviewNonwork}/nonwork`, "已标记为非工作");
});

refresh().catch(error => setLog(error.message, true));
setInterval(() => refresh().catch(error => setLog(error.message, true)), 10000);
