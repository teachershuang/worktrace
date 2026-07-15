const pet = {
  expanded: false,
  busy: false,
  toastTimer: null,
  lastStatus: null,
};

const els = {
  body: document.body,
  toggle: document.querySelector("#pet-toggle"),
  assistant: document.querySelector("#pet-assistant"),
  badge: document.querySelector("#pet-badge"),
  panel: document.querySelector("#quick-panel"),
  close: document.querySelector("#panel-close"),
  title: document.querySelector("#panel-title"),
  state: document.querySelector("#panel-state"),
  detail: document.querySelector("#panel-detail"),
  reviewCount: document.querySelector("#review-count"),
  lastActivity: document.querySelector("#last-activity"),
  toast: document.querySelector("#pet-toast"),
  actions: Array.from(document.querySelectorAll("[data-action]")),
};

const assetNames = new Set([
  "assistant-main.png",
  "assistant-rest.png",
  "assistant-sidebar.png",
  "assistant-tile.png",
]);

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败 (${response.status})`);
  }
  return payload;
}

function renderStatus(status) {
  pet.lastStatus = status;
  const view = status.pet_state || {
    kind: "standby",
    label: "待命中",
    detail: "点击桌宠打开快捷面板",
    asset: "assistant-sidebar.png",
  };
  const asset = assetNames.has(view.asset) ? view.asset : "assistant-sidebar.png";

  els.body.dataset.state = view.kind;
  els.assistant.src = `/static/assets/mascot/${asset}`;
  els.badge.textContent = view.label;
  els.title.textContent = headlineFor(view.kind);
  els.state.textContent = view.label;
  els.detail.textContent = view.detail;
  els.reviewCount.textContent = String(status.review_count || 0);
  els.lastActivity.textContent = formatLastActivity(status.last_activity);

  const startButton = els.actions.find((button) => button.dataset.action === "start");
  const pauseButton = els.actions.find((button) => button.dataset.action === "pause");
  if (startButton) startButton.disabled = pet.busy || (status.loop_running && !status.paused);
  if (pauseButton) pauseButton.disabled = pet.busy || !status.loop_running || status.paused;
}

function headlineFor(kind) {
  return {
    recording: "专注记录中",
    paused: "记录已暂停",
    review: "有事件待确认",
    error: "服务需要检查",
    waiting: "等待工作时段",
    standby: "工作时段待命",
  }[kind] || "WorkTrace 助手";
}

function formatLastActivity(activity) {
  if (!activity || !activity.status) return "尚未记录";
  const labels = {
    recorded: "已记录",
    review: "待确认",
    skipped: "已跳过",
    paused: "已暂停",
    failed: "记录失败",
  };
  const time = activity.at && activity.at.length >= 16 ? activity.at.slice(11, 16) : "--:--";
  return `${time} ${labels[activity.status] || activity.status}`;
}

async function refreshStatus() {
  try {
    renderStatus(await request("/api/status"));
  } catch (error) {
    renderStatus({
      loop_running: false,
      paused: false,
      review_count: 0,
      last_activity: null,
      pet_state: {
        kind: "error",
        label: "控制台异常",
        detail: error.message || "无法连接本地 WorkTrace 服务",
        asset: "assistant-rest.png",
      },
    });
  }
}

async function setPanel(expanded) {
  if (pet.expanded === expanded) return;
  if (!expanded) {
    els.body.classList.remove("panel-open");
    els.panel.setAttribute("aria-hidden", "true");
    els.toggle.setAttribute("aria-expanded", "false");
  }
  try {
    await callBridge("set_expanded", expanded);
  } catch (error) {
    showToast(error.message || "无法调整桌宠窗口", true);
    return;
  }
  pet.expanded = expanded;
  if (expanded) {
    els.body.classList.add("panel-open");
    els.panel.setAttribute("aria-hidden", "false");
    els.toggle.setAttribute("aria-expanded", "true");
    await refreshStatus();
  }
}

async function callBridge(method, ...args) {
  if (!window.pywebview?.api?.[method]) {
    throw new Error("桌面窗口桥接尚未就绪，请稍后重试");
  }
  return window.pywebview.api[method](...args);
}

async function runAction(action, button) {
  if (pet.busy) return;
  pet.busy = true;
  setBusy(true, button);
  try {
    if (action === "console") {
      await callBridge("show_console");
      showToast("已打开完整控制台");
    } else {
      const actions = {
        start: ["/api/recording/start-or-resume", "记录已开始 / 恢复"],
        pause: ["/api/recording/pause", "记录已暂停"],
        record: ["/api/record-once", "本次屏幕记录已完成"],
        daily: ["/api/reports/daily", "今日日报已生成"],
      };
      const target = actions[action];
      if (!target) throw new Error("未知操作");
      await request(target[0], { method: "POST" });
      showToast(target[1]);
    }
  } catch (error) {
    showToast(error.message || "操作失败", true);
  } finally {
    pet.busy = false;
    setBusy(false, button);
    await refreshStatus();
  }
}

function setBusy(busy, activeButton) {
  for (const button of els.actions) {
    button.disabled = busy;
  }
  if (activeButton) activeButton.textContent = busy ? "处理中..." : activeButton.dataset.label;
  if (!busy && pet.lastStatus) renderStatus(pet.lastStatus);
}

function showToast(message, isError = false) {
  window.clearTimeout(pet.toastTimer);
  els.toast.textContent = message;
  els.toast.classList.toggle("error", isError);
  els.toast.classList.add("visible");
  pet.toastTimer = window.setTimeout(() => els.toast.classList.remove("visible"), 3200);
}

els.toggle.addEventListener("click", () => setPanel(!pet.expanded));
els.close.addEventListener("click", () => setPanel(false));
els.panel.addEventListener("click", (event) => event.stopPropagation());

for (const button of els.actions) {
  button.dataset.label = button.textContent;
  button.addEventListener("click", () => runAction(button.dataset.action, button));
}

window.addEventListener("pywebviewready", refreshStatus);
window.setInterval(refreshStatus, 2500);
refreshStatus();
