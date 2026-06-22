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
const reportEditorEl = document.querySelector("#report-editor");
const settingsGridEl = document.querySelector("#settings-grid");
const desktopActionsEl = document.querySelector("#desktop-actions");
const diagnosticsGridEl = document.querySelector("#diagnostics-grid");
const reviewDateEl = document.querySelector("#review-date");
const reviewSearchEl = document.querySelector("#review-search");

let reviewItems = [];
let selectedReviewIds = new Set();
let currentReportKind = "daily";

function setLog(text, failed = false) {
  logEl.textContent = text;
  logEl.style.color = failed ? "var(--red)" : "var(--muted)";
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    method: "GET",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function humanizeError(message) {
  if (!message) return "操作失败，请查看日志。";
  if (message.includes("401") || message.includes("Unauthorized")) {
    return "LLM 服务认证失败，请检查 API Key 或模型网关鉴权配置。";
  }
  if (message.includes("no effective work events found for daily report")) {
    return "今天还没有可用于生成日报的有效工作事件。请先记录一次，或在待确认列表中标记工作事件。";
  }
  if (message.includes("no effective work events or daily reports found for weekly report")) {
    return "本周还没有可用于生成周报的日报或有效时间轴。请先记录工作事件并生成日报。";
  }
  return message;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function setPill(element, text, mode = "muted") {
  element.className = `pill ${mode}`;
  element.textContent = text;
}

function renderSettingItem(label, value) {
  return `
    <div class="setting-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderDesktopCard(title, body, actions = "") {
  return `
    <div class="desktop-card">
      <strong>${escapeHtml(title)}</strong>
      <p class="muted">${escapeHtml(body)}</p>
      ${actions}
    </div>
  `;
}

function selectedReviewDate() {
  return reviewDateEl?.value || new Date().toISOString().slice(0, 10);
}

function renderTimeline(items) {
  timelineListEl.innerHTML = items.slice(-8).reverse().map(item => `
    <li class="event-item">
      <span class="event-time">${escapeHtml(item.start_at.slice(11, 16))}</span>
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <span class="muted">${escapeHtml(item.summary || "")}</span>
      </div>
    </li>
  `).join("") || `<li class="muted">暂无有效工作事件</li>`;
}

function renderReview(items) {
  const keyword = (reviewSearchEl?.value || "").trim().toLowerCase();
  const filtered = items.filter(item => {
    if (!keyword) return true;
    const decision = item.classification || {};
    return [
      decision.title,
      decision.summary,
      decision.project,
      decision.category,
      item.window_title,
      item.app_name,
    ].some(value => String(value || "").toLowerCase().includes(keyword));
  });

  reviewListEl.innerHTML = filtered.map(item => {
    const decision = item.classification || {};
    const eventId = item.id || "";
    return `
      <div class="review-row">
        <label class="check-cell">
          <input type="checkbox" data-review-check="${escapeHtml(eventId)}" ${selectedReviewIds.has(eventId) ? "checked" : ""} />
        </label>
        <span class="event-time">${escapeHtml((item.captured_at || "").slice(11, 16))}</span>
        <div>
          <strong>${escapeHtml(decision.title || "-")}</strong>
          <div class="muted">${escapeHtml(decision.summary || "")}</div>
          <small>${escapeHtml(decision.project || "未识别项目")} · ${escapeHtml(decision.category || "待判断")}</small>
        </div>
        <span>${escapeHtml(decision.confidence ?? "-")}</span>
        <div class="review-actions">
          <button class="quick-button" data-review-work="${escapeHtml(eventId)}">工作</button>
          <button class="quick-button danger" data-review-nonwork="${escapeHtml(eventId)}">非工作</button>
        </div>
      </div>
    `;
  }).join("") || `<div class="muted">暂无待确认事件</div>`;
}

function renderDiagnostics(payload) {
  const ocrFailed = payload.ocr.consecutive_failures > 0;
  const storageBad = payload.storage.some(item => !item.exists || !item.writable);
  const cards = [
    {
      title: "OCR",
      mode: ocrFailed ? "bad" : "ok",
      body: ocrFailed ? `连续失败 ${payload.ocr.consecutive_failures} 次` : `${payload.ocr.protocol} 正常待命`,
      meta: payload.ocr.url,
    },
    {
      title: "LLM",
      mode: "muted",
      body: payload.llm.model,
      meta: payload.llm.base_url,
    },
    {
      title: "本地存储",
      mode: storageBad ? "bad" : "ok",
      body: storageBad ? "存在不可写目录" : "目录可写",
      meta: payload.storage.map(item => `${item.name}: ${item.writable ? "可写" : "异常"}`).join(" / "),
    },
    {
      title: "今日事件",
      mode: payload.events.review_today ? "warn" : "ok",
      body: `${payload.events.effective_today} 个有效，${payload.events.review_today} 个待确认`,
      meta: `${payload.events.raw_today} 条原始记录`,
    },
  ];
  diagnosticsGridEl.innerHTML = cards.map(card => `
    <div class="diagnostic-card ${card.mode}">
      <strong>${escapeHtml(card.title)}</strong>
      <span>${escapeHtml(card.body)}</span>
      <small>${escapeHtml(card.meta)}</small>
    </div>
  `).join("");
}

function renderReportBlock(label, report) {
  if (!report.exists) {
    return `## ${label}\n暂无已生成报告`;
  }
  return `## ${label}\n路径: ${report.path}\n更新时间: ${report.updated_at || "-"}\n\n${report.content}`;
}

function renderAutostart(status) {
  if (!status.supported) {
    desktopActionsEl.innerHTML = renderDesktopCard(
      "开机自启",
      status.reason || "当前平台暂不支持开机自启。",
    );
    return;
  }

  const body = status.enabled
    ? `已启用，登录 Windows 后将以托盘模式启动。启动项文件: ${status.startup_file || "-"}`
    : "未启用。启用后将在登录 Windows 时自动启动 WorkTrace 托盘模式。";
  const actions = status.enabled
    ? `<div class="button-row"><button class="quick-button danger" data-action="autostart-disable">关闭开机自启</button></div>`
    : `<div class="button-row"><button class="quick-button" data-action="autostart-enable">启用开机自启</button></div>`;
  desktopActionsEl.innerHTML = renderDesktopCard("开机自启", body, actions);
}

async function refresh() {
  const day = selectedReviewDate();
  const [status, timeline, review] = await Promise.all([
    request("/api/status"),
    request(`/api/timeline/today?day=${encodeURIComponent(day)}`),
    request(`/api/review?day=${encodeURIComponent(day)}`),
  ]);

  const now = new Date(status.now);
  todayDateEl.textContent = now.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "long",
  });

  const runningText = status.loop_running ? "记录中" : "未运行";
  const mode = status.paused ? "warn" : status.loop_running ? "ok" : "muted";
  setPill(statusPillEl, status.paused ? "已暂停" : runningText, mode);
  sideStatusEl.textContent = status.paused ? "暂停中" : runningText;
  recordStateEl.textContent = status.paused ? "暂停中" : runningText;
  recordCopyEl.textContent = status.in_work_period ? "处于配置的工作时间段" : "当前不在工作时间段";
  recordDotEl.style.background = status.loop_running && !status.paused ? "var(--green)" : "var(--amber)";

  idleTimeEl.textContent = status.idle_seconds === null ? "未知" : `${Math.round(status.idle_seconds)}s`;
  intervalEl.textContent = `${status.screenshot_interval_seconds}s`;
  metricDurationEl.textContent = formatDuration(timelineMinutes(timeline.items));
  metricEventsEl.textContent = String(timeline.items.length);
  metricReviewEl.textContent = String(review.items.length);
  metricOcrEl.textContent = status.ocr_consecutive_failures ? `异常 ${status.ocr_consecutive_failures}` : "正常";

  reviewItems = review.items;
  selectedReviewIds = new Set([...selectedReviewIds].filter(id => reviewItems.some(item => item.id === id)));
  renderTimeline(timeline.items);
  renderReview(reviewItems);
}

async function refreshSettings() {
  const [config, autostart] = await Promise.all([
    request("/api/config/summary"),
    request("/api/autostart"),
  ]);

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

  renderAutostart(autostart);
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
    const active = currentReportKind === "weekly" ? weekly : daily;
    reportEditorEl.value = active.content || "";
  } catch (error) {
    reportPreviewEl.textContent = `报告读取失败: ${humanizeError(error.message)}`;
  }
}

async function refreshDiagnostics() {
  const payload = await request("/api/diagnostics");
  renderDiagnostics(payload);
}

async function post(path, okText, button = null) {
  try {
    if (button) {
      button.disabled = true;
      button.dataset.busy = "true";
    }
    setLog("处理中...");
    const result = await request(path, { method: "POST" });
    const detail = result.message || result.path;
    setLog(detail ? `${okText}: ${detail}` : okText);
    await refresh();
    if (path.startsWith("/api/reports/")) {
      await refreshReports();
    }
    if (path.startsWith("/api/autostart/")) {
      await refreshSettings();
    }
    if (path.startsWith("/api/test/")) {
      await refreshDiagnostics();
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

async function postJson(path, payload, okText, button = null) {
  try {
    if (button) {
      button.disabled = true;
      button.dataset.busy = "true";
    }
    setLog("处理中...");
    const result = await request(path, { method: "POST", body: JSON.stringify(payload) });
    setLog(result.count !== undefined ? `${okText}: ${result.count} 条` : okText);
    selectedReviewIds.clear();
    await refresh();
    await refreshDiagnostics();
  } catch (error) {
    setLog(humanizeError(error.message), true);
  } finally {
    if (button) {
      button.disabled = false;
      delete button.dataset.busy;
    }
  }
}

async function saveCurrentReport(button = null) {
  try {
    if (button) {
      button.disabled = true;
      button.dataset.busy = "true";
    }
    const result = await request(`/api/reports/latest/${currentReportKind}`, {
      method: "PUT",
      body: JSON.stringify({ content: reportEditorEl.value }),
    });
    setLog(`报告已保存: ${result.path}`);
    await refreshReports();
  } catch (error) {
    setLog(humanizeError(error.message), true);
  } finally {
    if (button) {
      button.disabled = false;
      delete button.dataset.busy;
    }
  }
}

document.addEventListener("click", event => {
  const target = event.target.closest("button");
  if (!target) return;

  const action = target.dataset.action;
  const reviewWork = target.dataset.reviewWork;
  const reviewNonwork = target.dataset.reviewNonwork;

  if (target.dataset.refresh !== undefined) {
    refresh().catch(error => setLog(humanizeError(error.message), true));
    return;
  }

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
  if (action === "autostart-enable") post("/api/autostart/enable", "已启用开机自启", target);
  if (action === "autostart-disable") post("/api/autostart/disable", "已关闭开机自启", target);
  if (action === "refresh-diagnostics") refreshDiagnostics().then(() => setLog("诊断信息已刷新"));
  if (action === "edit-daily") {
    currentReportKind = "daily";
    refreshReports().then(() => setLog("已载入日报编辑器"));
  }
  if (action === "edit-weekly") {
    currentReportKind = "weekly";
    refreshReports().then(() => setLog("已载入周报编辑器"));
  }
  if (action === "save-report") saveCurrentReport(target);
  if (action === "review-select-all") {
    const visibleIds = [...document.querySelectorAll("[data-review-check]")].map(input => input.dataset.reviewCheck);
    const allSelected = visibleIds.length > 0 && visibleIds.every(id => selectedReviewIds.has(id));
    visibleIds.forEach(id => (allSelected ? selectedReviewIds.delete(id) : selectedReviewIds.add(id)));
    renderReview(reviewItems);
  }
  if (action === "review-bulk-work") {
    if (!selectedReviewIds.size) {
      setLog("请先选择待确认事件，或点击全选。", true);
      return;
    }
    postJson("/api/review/bulk/work", { ids: [...selectedReviewIds], date: selectedReviewDate() }, "已批量标记为工作", target);
  }
  if (action === "review-bulk-nonwork") {
    if (!selectedReviewIds.size) {
      setLog("请先选择待确认事件，或点击全选。", true);
      return;
    }
    postJson("/api/review/bulk/nonwork", { ids: [...selectedReviewIds], date: selectedReviewDate() }, "已批量标记为非工作", target);
  }
  if (reviewWork) post(`/api/review/${reviewWork}/work`, "已标记为工作", target);
  if (reviewNonwork) post(`/api/review/${reviewNonwork}/nonwork`, "已标记为非工作", target);
});

document.addEventListener("change", event => {
  const target = event.target;
  if (target.matches("[data-review-check]")) {
    if (target.checked) {
      selectedReviewIds.add(target.dataset.reviewCheck);
    } else {
      selectedReviewIds.delete(target.dataset.reviewCheck);
    }
  }
  if (target === reviewDateEl) {
    selectedReviewIds.clear();
    refresh().catch(error => setLog(humanizeError(error.message), true));
  }
});

reviewSearchEl?.addEventListener("input", () => renderReview(reviewItems));

reviewDateEl.value = new Date().toISOString().slice(0, 10);
refresh().catch(error => setLog(humanizeError(error.message), true));
refreshSettings().catch(error => setLog(humanizeError(error.message), true));
refreshReports().catch(error => setLog(humanizeError(error.message), true));
refreshDiagnostics().catch(error => setLog(humanizeError(error.message), true));
setInterval(() => refresh().catch(error => setLog(humanizeError(error.message), true)), 10000);
