// ── State ──────────────────────────────────
let agents = [];
let selectedAgents = new Set();
let active = false;
let paused = false;
let evtSource = null;
let editingName = null;

// ── Init ──────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await fetchAgents();
  fetchHistory();
  connectSSE();
  checkStatus();
});

// ── Agents ─────────────────────────────────
async function fetchAgents() {
  const res = await fetch("/api/agents");
  agents = await res.json();
  renderAgentList();
}

function renderAgentList() {
  const list = document.getElementById("agent-list");
  list.innerHTML = "";
  agents.forEach((a) => {
    if (!selectedAgents.has(a.name)) selectedAgents.add(a.name);
    const card = document.createElement("div");
    card.className = "agent-card selected";
    card.dataset.name = a.name;
    card.innerHTML = `
      <div class="agent-avatar" style="background:${a.color}30">${a.avatar}</div>
      <div class="agent-info">
        <div class="name" style="color:${a.color}">${esc(a.name)}</div>
        <div class="desc">${esc(a.personality.slice(0, 40))}…</div>
      </div>
      <div class="card-actions">
        <button class="icon-btn" title="编辑" onclick="event.stopPropagation();showEditForm('${esc(a.name)}')">✏️</button>
        <button class="icon-btn" title="删除" onclick="event.stopPropagation();deleteAgent('${esc(a.name)}')">✕</button>
      </div>`;
    card.addEventListener("click", () => toggleAgent(a.name, card));
    list.appendChild(card);
  });
}

function toggleAgent(name, card) {
  if (active) return;
  if (selectedAgents.has(name)) {
    selectedAgents.delete(name);
    card.classList.remove("selected");
  } else {
    selectedAgents.add(name);
    card.classList.add("selected");
  }
}

// ── Agent CRUD ─────────────────────────────
function showAddForm() {
  if (active) return;
  editingName = null;
  document.getElementById("form-title").textContent = "添加 Agent";
  document.getElementById("f-name").value = "";
  document.getElementById("f-personality").value = "";
  document.getElementById("f-avatar").value = "🤖";
  document.getElementById("f-color").value = "#6366f1";
  document.getElementById("agent-form").style.display = "";
}

function showEditForm(name) {
  if (active) return;
  const a = agents.find((x) => x.name === name);
  if (!a) return;
  editingName = name;
  document.getElementById("form-title").textContent = "编辑 Agent";
  document.getElementById("f-name").value = a.name;
  document.getElementById("f-personality").value = a.personality;
  document.getElementById("f-avatar").value = a.avatar;
  document.getElementById("f-color").value = a.color;
  document.getElementById("agent-form").style.display = "";
}

function hideForm() {
  document.getElementById("agent-form").style.display = "none";
  editingName = null;
}

async function submitForm() {
  const name = document.getElementById("f-name").value.trim();
  const personality = document.getElementById("f-personality").value.trim();
  const avatar = document.getElementById("f-avatar").value.trim() || "🤖";
  const color = document.getElementById("f-color").value;

  if (!name || !personality) {
    alert("名字和人设不能为空");
    return;
  }

  let res;
  if (editingName) {
    res = await fetch(`/api/agents/${encodeURIComponent(editingName)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, personality, avatar, color }),
    });
  } else {
    res = await fetch("/api/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, personality, avatar, color }),
    });
  }

  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "操作失败");
    return;
  }

  hideForm();
  await fetchAgents();
}

async function deleteAgent(name) {
  if (active) return;
  if (!confirm(`确定删除 Agent「${name}」？`)) return;
  const res = await fetch(`/api/agents/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "删除失败");
    return;
  }
  selectedAgents.delete(name);
  await fetchAgents();
}

async function resetAgents() {
  if (active) return;
  if (!confirm("恢复默认 Agent？自定义 Agent 将被删除。")) return;
  await fetch("/api/agents/reset", { method: "POST" });
  selectedAgents.clear();
  await fetchAgents();
}

// ── History ────────────────────────────────
async function fetchHistory() {
  const res = await fetch("/api/history");
  const messages = await res.json();
  const container = document.getElementById("messages");
  container.innerHTML = "";
  messages.forEach((m) => renderMessage(m));
  scrollToBottom();
}

// ── SSE ────────────────────────────────────
function connectSSE() {
  evtSource = new EventSource("/api/events");

  evtSource.addEventListener("message", (e) => {
    const msg = JSON.parse(e.data);
    renderMessage(msg);
    scrollToBottom();
  });

  evtSource.addEventListener("status", (e) => {
    const data = JSON.parse(e.data);
    setStatus(data.active, data.paused);
  });

  evtSource.addEventListener("agents_changed", () => {
    fetchAgents();
  });
}

// ── User message ───────────────────────────
async function sendUserMessage(e) {
  e.preventDefault();
  const input = document.getElementById("user-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  const res = await fetch("/api/user-message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "发送失败");
  }
}

// ── Chat actions ───────────────────────────
async function startChat() {
  if (active) return;
  if (selectedAgents.size < 2) {
    alert("至少选择 2 个 Agent 才能聊天");
    return;
  }

  const topic = document.getElementById("topic").value.trim();
  const rounds = parseInt(document.getElementById("rounds").value) || 3;

  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agents: [...selectedAgents],
      topic: topic || null,
      rounds,
    }),
  });

  if (!res.ok) {
    const err = await res.json();
    alert(err.error || "启动失败");
    return;
  }

  setStatus(true, false);
}

async function pauseChat() {
  await fetch("/api/pause", { method: "POST" });
}

async function resumeChat() {
  await fetch("/api/resume", { method: "POST" });
}

async function stopChat() {
  await fetch("/api/stop", { method: "POST" });
}

async function clearChat() {
  await fetch("/api/clear", { method: "POST" });
  document.getElementById("messages").innerHTML = "";
  setStatus(false, false);
}

async function checkStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  setStatus(data.active, data.paused);
}

// ── Render messages ─────────────────────────
function renderMessage(msg) {
  const container = document.getElementById("messages");
  const div = document.createElement("div");

  const now = new Date();
  const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

  if (msg.type === "summary") {
    div.className = "msg summary";
    div.innerHTML = `
      <div class="summary-card">
        <div class="summary-header">📋 讨论总结</div>
        <div class="summary-body">${formatMarkdown(msg.text)}</div>
      </div>`;
  } else if (msg.type === "system") {
    div.className = "msg system";
    div.innerHTML = `<div class="msg-text">${esc(msg.text)}</div>`;
  } else if (msg.type === "user") {
    div.className = "msg chat user-msg";
    div.innerHTML = `
      <div class="msg-avatar" style="background:${msg.color}25">${msg.avatar}</div>
      <div class="msg-body">
        <div class="msg-header">
          <span class="msg-name" style="color:${msg.color}">${esc(msg.agent)}</span>
          <span class="msg-time">${time}</span>
        </div>
        <div class="msg-text">${esc(msg.text)}</div>
      </div>`;
  } else {
    div.className = "msg chat";
    div.innerHTML = `
      <div class="msg-avatar" style="background:${msg.color}25">${msg.avatar}</div>
      <div class="msg-body">
        <div class="msg-header">
          <span class="msg-name" style="color:${msg.color}">${esc(msg.agent)}</span>
          <span class="msg-time">${time}</span>
        </div>
        <div class="msg-text">${esc(msg.text)}</div>
      </div>`;
  }

  container.appendChild(div);
}

function setStatus(isActive, isPaused) {
  active = isActive;
  paused = isPaused || false;

  const dot = document.getElementById("status-indicator");
  const text = document.getElementById("status-text");
  const btnStart = document.getElementById("btn-start");
  const btnPause = document.getElementById("btn-pause");
  const btnResume = document.getElementById("btn-resume");
  const btnStop = document.getElementById("btn-stop");
  const inputBar = document.getElementById("user-input-bar");

  if (isActive && paused) {
    dot.className = "dot paused";
    text.textContent = "已暂停 — 输入你的观点后继续";
  } else if (isActive) {
    dot.className = "dot active";
    text.textContent = "讨论进行中…";
  } else {
    dot.className = "dot idle";
    text.textContent = "等待开始";
  }

  btnStart.disabled = isActive;
  btnPause.disabled = !isActive || paused;
  btnPause.style.display = paused ? "none" : "";
  btnResume.style.display = paused ? "" : "none";
  btnStop.disabled = !isActive;
  inputBar.style.display = isActive ? "flex" : "none";
}

function scrollToBottom() {
  const area = document.getElementById("chat-area");
  requestAnimationFrame(() => {
    area.scrollTop = area.scrollHeight;
  });
}

function esc(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function formatMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}
