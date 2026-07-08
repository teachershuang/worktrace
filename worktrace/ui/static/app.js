const els = {
  log: document.querySelector("#log"),
  sideStatus: document.querySelector("#side-status"),
  statusPill: document.querySelector("#state-pill"),
  recordDot: document.querySelector("#record-dot"),
  recordState: document.querySelector("#record-state"),
  recordCopy: document.querySelector("#record-copy"),
  lastActivityStatus: document.querySelector("#last-activity-status"),
  lastActivityReason: document.querySelector("#last-activity-reason"),
  todayDate: document.querySelector("#today-date"),
  idleTime: document.querySelector("#idle-time"),
  interval: document.querySelector("#interval"),
  metricDuration: document.querySelector("#metric-duration"),
  metricEvents: document.querySelector("#metric-events"),
  metricReview: document.querySelector("#metric-review"),
  metricOcr: document.querySelector("#metric-ocr"),
  timelineList: document.querySelector("#timeline-list"),
  reviewList: document.querySelector("#review-list"),
  reportPreview: document.querySelector("#report-preview"),
  reportEditor: document.querySelector("#report-editor"),
  settingsGrid: document.querySelector("#settings-grid"),
  desktopActions: document.querySelector("#desktop-actions"),
  diagnosticsGrid: document.querySelector("#diagnostics-grid"),
  reviewDate: document.querySelector("#review-date"),
  reviewSearch: document.querySelector("#review-search"),
  configForm: document.querySelector("#config-form"),
  viewTitle: document.querySelector("#view-title"),
};

const viewTitles = {
  overview: "今日概览",
  timeline: "时间轴",
  reports: "报告编辑",
  review: "待确认",
  settings: "接口配置",
  diagnostics: "运行诊断",
};

let reviewItems = [];
let selectedReviewIds = new Set();
let currentReportKind = "daily";

function setLog(text, failed = false) {
  if (!els.log) return;
  els.log.textContent = text;
  els.log.style.color = failed ? "var(--red)" : "var(--muted)";
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
  if (message.includes("401") || message.includes("Unauthorized") || message.includes("认证失败")) {
    return "LLM 服务认证失败，请检查 API Key 或模型网关授权配置。";
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
  if (!element) return;
  element.className = `pill ${mode}`;
  element.textContent = text;
}

function activityLabel(status) {
  return {
    recorded: "已记录",
    review: "待确认",
    skipped: "已跳过",
    paused: "已暂停",
    failed: "记录失败",
  }[status] || status || "尚未记录";
}

function formatActivityTime(value) {
  if (!value) return "--:--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).slice(11, 16) || "--:--";
  }
  return parsed.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function renderActivitySummary(activity) {
  const status = activity?.status || null;
  return {
    label: activityLabel(status),
    time: formatActivityTime(activity?.at),
    reason: activity?.reason || "后台完成一次记录后会显示写入、待确认、跳过或失败原因。",
    mode: status === "failed" ? "bad" : status === "review" ? "warn" : status === "recorded" ? "ok" : "muted",
  };
}

function renderServiceCheck(check) {
  if (!check) return "尚未测试";
  const state = check.ok ? "成功" : "失败";
  const elapsed = Number.isFinite(check.elapsed_ms) ? `${check.elapsed_ms}ms` : "-";
  return `${state} · ${elapsed} · ${check.checked_at || "-"}`;
}

function selectedReviewDate() {
  return els.reviewDate?.value || new Date().toISOString().slice(0, 10);
}

function switchView(name) {
  document.querySelectorAll(".view-section").forEach(section => {
    section.classList.toggle("is-active", section.id === `view-${name}`);
  });
  document.querySelectorAll("[data-view-target]").forEach(item => {
    item.classList.toggle("is-active", item.dataset.viewTarget === name);
  });
  if (els.viewTitle) els.viewTitle.textContent = viewTitles[name] || "WorkTrace";
}

function renderTimeline(items) {
  els.timelineList.innerHTML = items.slice(-10).reverse().map(item => `
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
  const keyword = (els.reviewSearch?.value || "").trim().toLowerCase();
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

  els.reviewList.innerHTML = filtered.map(item => {
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
  const activity = renderActivitySummary(payload.last_activity);
  const cards = [
    { title: "最近活动", mode: activity.mode, body: `${activity.time} · ${activity.label}`, meta: activity.reason },
    { title: "OCR", mode: ocrFailed ? "bad" : "ok", body: ocrFailed ? `连续失败 ${payload.ocr.consecutive_failures} 次` : `${payload.ocr.protocol} 正常待命`, meta: payload.ocr.url },
    { title: "LLM", mode: "muted", body: payload.llm.model, meta: payload.llm.base_url },
    { title: "本地存储", mode: storageBad ? "bad" : "ok", body: storageBad ? "存在不可写目录" : "目录可写", meta: payload.storage.map(item => `${item.name}: ${item.writable ? "可写" : "异常"}`).join(" / ") },
    { title: "今日事件", mode: payload.events.review_today ? "warn" : "ok", body: `${payload.events.effective_today} 个有效，${payload.events.review_today} 个待确认`, meta: `${payload.events.raw_today} 条原始记录` },
  ];
  els.diagnosticsGrid.innerHTML = cards.map(card => `
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
    els.desktopActions.innerHTML = renderDesktopCard("开机自启", status.reason || "当前平台暂不支持开机自启。");
    return;
  }
  const body = status.enabled
    ? `已启用，登录 Windows 后将以托盘模式启动。启动项文件: ${status.startup_file || "-"}`
    : "未启用。启用后将在登录 Windows 时自动启动 WorkTrace 托盘模式。";
  const actions = status.enabled
    ? `<div class="button-row"><button class="quick-button danger" data-action="autostart-disable">关闭开机自启</button></div>`
    : `<div class="button-row"><button class="quick-button" data-action="autostart-enable">启用开机自启</button></div>`;
  els.desktopActions.innerHTML = renderDesktopCard("开机自启", body, actions);
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

function renderSettingItem(label, value) {
  return `
    <div class="setting-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function setFormValue(name, value) {
  const input = els.configForm?.elements?.[name];
  if (!input) return;
  if (input.type === "checkbox") {
    input.checked = Boolean(value);
  } else if (Array.isArray(value)) {
    input.value = value.join(",");
  } else {
    input.value = value ?? "";
  }
}

function readFormValue(name) {
  const input = els.configForm?.elements?.[name];
  if (!input) return "";
  return input.type === "checkbox" ? input.checked : input.value;
}

function fillConfigForm(config) {
  setFormValue("llm.base_url", config.llm.base_url);
  setFormValue("llm.api_key", config.llm.api_key);
  setFormValue("llm.model", config.llm.model);
  setFormValue("llm.timeout_seconds", config.llm.timeout_seconds);
  setFormValue("ocr.url", config.ocr.url);
  setFormValue("ocr.protocol", config.ocr.protocol);
  setFormValue("ocr.timeout_seconds", config.ocr.timeout_seconds);
  setFormValue("recording.work_periods", config.recording.work_periods);
  setFormValue("recording.screenshot_interval_seconds", config.recording.screenshot_interval_seconds);
  setFormValue("recording.idle_skip_minutes", config.recording.idle_skip_minutes);
  setFormValue("recording.enable_tray", config.recording.enable_tray);
  setFormValue("storage.data_dir", config.storage.data_dir);
  setFormValue("storage.report_output_dir", config.storage.report_output_dir);
  setFormValue("storage.log_dir", config.storage.log_dir);
}

function collectConfigForm() {
  return {
    llm: {
      base_url: readFormValue("llm.base_url"),
      api_key: readFormValue("llm.api_key"),
      model: readFormValue("llm.model"),
      timeout_seconds: Number(readFormValue("llm.timeout_seconds")),
    },
    ocr: {
      url: readFormValue("ocr.url"),
      protocol: readFormValue("ocr.protocol"),
      timeout_seconds: Number(readFormValue("ocr.timeout_seconds")),
    },
    recording: {
      work_periods: readFormValue("recording.work_periods"),
      screenshot_interval_seconds: Number(readFormValue("recording.screenshot_interval_seconds")),
      idle_skip_minutes: Number(readFormValue("recording.idle_skip_minutes")),
      enable_tray: Boolean(readFormValue("recording.enable_tray")),
    },
    storage: {
      data_dir: readFormValue("storage.data_dir"),
      report_output_dir: readFormValue("storage.report_output_dir"),
      log_dir: readFormValue("storage.log_dir"),
    },
  };
}

async function refresh() {
  const day = selectedReviewDate();
  const [status, timeline, review] = await Promise.all([
    request("/api/status"),
    request(`/api/timeline/today?day=${encodeURIComponent(day)}`),
    request(`/api/review?day=${encodeURIComponent(day)}`),
  ]);

  const now = new Date(status.now);
  els.todayDate.textContent = now.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "long",
  });

  const runningText = status.loop_running ? "记录中" : "未运行";
  const mode = status.paused ? "warn" : status.loop_running ? "ok" : "muted";
  setPill(els.statusPill, status.paused ? "已暂停" : runningText, mode);
  els.sideStatus.textContent = status.paused ? "暂停中" : runningText;
  els.recordState.textContent = status.paused ? "暂停中" : runningText;
  els.recordCopy.textContent = status.in_work_period ? "处于配置的工作时间段" : "当前不在工作时间段";
  els.recordDot.style.background = status.loop_running && !status.paused ? "var(--green)" : "var(--amber)";

  const activity = renderActivitySummary(status.last_activity);
  els.lastActivityStatus.textContent = `${activity.time} · ${activity.label}`;
  els.lastActivityReason.textContent = activity.reason;
  els.idleTime.textContent = status.idle_seconds === null ? "未知" : `${Math.round(status.idle_seconds)}s`;
  els.interval.textContent = `${status.screenshot_interval_seconds}s`;
  els.metricDuration.textContent = formatDuration(timelineMinutes(timeline.items));
  els.metricEvents.textContent = String(timeline.items.length);
  els.metricReview.textContent = String(review.items.length);
  els.metricOcr.textContent = status.ocr_consecutive_failures ? `异常 ${status.ocr_consecutive_failures}` : "正常";

  reviewItems = review.items;
  selectedReviewIds = new Set([...selectedReviewIds].filter(id => reviewItems.some(item => item.id === id)));
  renderTimeline(timeline.items);
  renderReview(reviewItems);
}

async function refreshSettings() {
  const [summary, editable, autostart] = await Promise.all([
    request("/api/config/summary"),
    request("/api/config/editable"),
    request("/api/autostart"),
  ]);

  fillConfigForm(editable);
  els.settingsGrid.innerHTML = [
    renderSettingItem("配置文件", editable.config_path),
    renderSettingItem("大模型地址", summary.llm.base_url),
    renderSettingItem("大模型名称", summary.llm.model),
    renderSettingItem("OCR 地址", summary.ocr.url),
    renderSettingItem("OCR 协议", summary.ocr.protocol),
    renderSettingItem("工作时段", summary.recording.work_periods.join("，")),
    renderSettingItem("截图间隔", `${summary.recording.screenshot_interval_seconds}s`),
    renderSettingItem("空闲跳过", `${summary.recording.idle_skip_minutes} 分钟`),
  ].join("");
  renderAutostart(autostart);
}

async function refreshReports() {
  try {
    const [daily, weekly] = await Promise.all([
      request("/api/reports/latest/daily"),
      request("/api/reports/latest/weekly"),
    ]);
    els.reportPreview.textContent = [
      renderReportBlock("今日日报", daily),
      renderReportBlock("本周周报", weekly),
    ].join("\n\n---\n\n");
    const active = currentReportKind === "weekly" ? weekly : daily;
    els.reportEditor.value = active.content || "";
  } catch (error) {
    els.reportPreview.textContent = `报告读取失败: ${humanizeError(error.message)}`;
  }
}

function renderDiagnostics(payload) {
  const ocrFailed = payload.ocr.consecutive_failures > 0;
  const storageBad = payload.storage.some(item => !item.exists || !item.writable);
  const activity = renderActivitySummary(payload.last_activity);
  const ocrCheck = payload.ocr.last_check;
  const llmCheck = payload.llm.last_check;
  const cards = [
    { title: "最近活动", mode: activity.mode, body: `${activity.time} · ${activity.label}`, meta: activity.reason },
    {
      title: "OCR",
      mode: ocrFailed || ocrCheck?.ok === false ? "bad" : "ok",
      body: ocrFailed ? `连续失败 ${payload.ocr.consecutive_failures} 次` : `${payload.ocr.protocol} · ${renderServiceCheck(ocrCheck)}`,
      meta: payload.ocr.url,
    },
    {
      title: "LLM",
      mode: llmCheck?.ok === false ? "bad" : "muted",
      body: `${payload.llm.model} · ${renderServiceCheck(llmCheck)}`,
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
  els.diagnosticsGrid.innerHTML = cards.map(card => `
    <div class="diagnostic-card ${card.mode}">
      <strong>${escapeHtml(card.title)}</strong>
      <span>${escapeHtml(card.body)}</span>
      <small>${escapeHtml(card.meta)}</small>
    </div>
  `).join("");
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
    if (path.startsWith("/api/reports/")) await refreshReports();
    if (path.startsWith("/api/autostart/")) await refreshSettings();
    if (path.startsWith("/api/test/")) await refreshDiagnostics();
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
    if (button) button.disabled = true;
    const result = await request(`/api/reports/latest/${currentReportKind}`, {
      method: "PUT",
      body: JSON.stringify({ content: els.reportEditor.value }),
    });
    setLog(`报告已保存: ${result.path}`);
    await refreshReports();
  } catch (error) {
    setLog(humanizeError(error.message), true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function saveConfig(button = null) {
  try {
    if (button) button.disabled = true;
    const result = await request("/api/config/editable", {
      method: "PUT",
      body: JSON.stringify(collectConfigForm()),
    });
    setLog(result.message || "配置已保存，重启后生效。");
    await refreshSettings();
  } catch (error) {
    setLog(humanizeError(error.message), true);
  } finally {
    if (button) button.disabled = false;
  }
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-view-target]");
  if (nav) {
    switchView(nav.dataset.viewTarget);
    return;
  }

  const target = event.target.closest("button");
  if (!target) return;

  const action = target.dataset.action;
  const reviewWork = target.dataset.reviewWork;
  const reviewNonwork = target.dataset.reviewNonwork;

  if (target.dataset.refresh !== undefined) {
    refresh().catch(error => setLog(humanizeError(error.message), true));
    return;
  }

  if (action === "start-or-resume") post("/api/recording/start-or-resume", "记录已开始 / 恢复", target);
  if (action === "pause-recording") post("/api/recording/pause", "记录已暂停", target);
  if (action === "record-once") post("/api/record-once", "已完成一次记录", target);
  if (action === "daily") post("/api/reports/daily", "日报已生成", target);
  if (action === "weekly") post("/api/reports/weekly", "周报已生成", target);
  if (action === "refresh-reports") refreshReports().then(() => setLog("报告预览已刷新"));
  if (action === "test-ocr") post("/api/test/ocr", "OCR 测试完成", target);
  if (action === "test-llm") post("/api/test/llm", "LLM 测试完成", target);
  if (action === "autostart-enable") post("/api/autostart/enable", "已启用开机自启", target);
  if (action === "autostart-disable") post("/api/autostart/disable", "已关闭开机自启", target);
  if (action === "refresh-diagnostics") refreshDiagnostics().then(() => setLog("诊断信息已刷新"));
  if (action === "reload-config-form") refreshSettings().then(() => setLog("配置已重新读取"));
  if (action === "save-config") saveConfig(target);
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
  if (target === els.reviewDate) {
    selectedReviewIds.clear();
    refresh().catch(error => setLog(humanizeError(error.message), true));
  }
});

els.reviewSearch?.addEventListener("input", () => renderReview(reviewItems));
els.reviewDate.value = new Date().toISOString().slice(0, 10);

switchView("overview");
refresh().catch(error => setLog(humanizeError(error.message), true));
refreshSettings().catch(error => setLog(humanizeError(error.message), true));
refreshReports().catch(error => setLog(humanizeError(error.message), true));
refreshDiagnostics().catch(error => setLog(humanizeError(error.message), true));
setInterval(() => refresh().catch(error => setLog(humanizeError(error.message), true)), 10000);
