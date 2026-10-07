/* =====================================================
   Research Agent — frontend v4
   SSE streaming + DB polling fallback
   ===================================================== */

const API = {
  chats: "/api/chats",
  chat: (id) => `/api/chats/${id}`,
  messages: (id) => `/api/chats/${id}/messages`,
  research: "/api/chat",
};

let activeChatId = null;
let currentController = null;

/* ---------- DOM ---------- */
const chatsList = document.getElementById("chats-list");
const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const stopBtn = document.getElementById("stop-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const welcomeEl = document.getElementById("welcome");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.querySelector(".sidebar");

/* ---------- Icons ---------- */
function refreshIcons() {
  if (window.lucide) {
    try { lucide.createIcons(); } catch (e) { console.warn("lucide:", e); }
  }
}

/* ---------- Utils ---------- */
function escapeHtml(t) {
  if (t == null) return "";
  return String(t).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[m]));
}

function renderMarkdown(text) {
  if (!text) return "";
  const raw = window.marked ? marked.parse(text) : escapeHtml(text);
  return window.DOMPurify ? DOMPurify.sanitize(raw) : raw;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStatus(text, color) {
  if (statusText) statusText.textContent = text;
  if (statusDot) {
    statusDot.style.background = color || "#10b981";
    statusDot.style.boxShadow = `0 0 8px ${color || "#10b981"}`;
  }
}

/* ---------- Premium AI search loader ---------- */
function renderAILoader(block) {
  if (!block) return;
  block.innerHTML = `
    <div class="ai-loader" role="status" aria-live="polite">
      <span class="ai-loader__glow"></span>
      <span class="ai-loader__shimmer"></span>
      <span class="ai-loader__text">
        Searching
        <span class="ai-loader__dots">
          <span></span><span></span><span></span>
        </span>
      </span>
    </div>
  `;
}

/* ---------- Welcome ---------- */
function showWelcome() {
  messagesEl.innerHTML = "";
  if (welcomeEl) {
    welcomeEl.style.display = "flex";
    messagesEl.appendChild(welcomeEl);
  }
  refreshIcons();
  if (input) input.focus();
}

function hideWelcome() {
  if (welcomeEl) welcomeEl.style.display = "none";
}

/* ---------- Chats sidebar ---------- */
async function loadChats() {
  try {
    const res = await fetch(API.chats);
    const chats = await res.json();
    renderChats(chats);
  } catch (e) {
    console.error("loadChats", e);
  }
}

function renderChats(chats) {
  chatsList.innerHTML = "";
  if (!chats.length) {
    const empty = document.createElement("div");
    empty.style.cssText = "padding:10px;color:#64748b;font-size:12px";
    empty.textContent = "No chats yet.";
    chatsList.appendChild(empty);
    return;
  }
  chats.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "chat-item" + (c.id === activeChatId ? " active" : "");
    btn.innerHTML = `
      <i data-lucide="message-square" style="width:13px;height:13px;opacity:.7"></i>
      <span class="title">${escapeHtml(c.title || "Untitled")}</span>
      <button class="del" title="Delete"><i data-lucide="trash-2" style="width:12px;height:12px"></i></button>
    `;
    btn.addEventListener("click", (ev) => {
      if (ev.target.closest(".del")) return;
      selectChat(c.id);
    });
    btn.querySelector(".del").addEventListener("click", (ev) => {
      ev.stopPropagation();
      deleteChat(c.id);
    });
    chatsList.appendChild(btn);
  });
  refreshIcons();
}

async function selectChat(id) {
  activeChatId = id;
  try {
    const res = await fetch(API.messages(id));
    const messages = await res.json();
    renderMessages(messages);
    loadChats();
    if (window.innerWidth <= 780 && sidebar) sidebar.classList.remove("open");
  } catch (e) {
    console.error("selectChat", e);
  }
}

async function deleteChat(id) {
  if (!confirm("Delete this chat?")) return;
  try {
    await fetch(API.chat(id), { method: "DELETE" });
    if (activeChatId === id) {
      activeChatId = null;
      showWelcome();
    }
    loadChats();
  } catch (e) {
    console.error("deleteChat", e);
  }
}

/* ---------- Messages render ---------- */
function renderMessages(messages) {
  messagesEl.innerHTML = "";
  if (!messages.length) {
    showWelcome();
    return;
  }
  messages.forEach((m) => {
    appendMessage(m.role, m.content, m.sources || []);
  });
  scrollToBottom();
  refreshIcons();
}

function appendMessage(role, content, sources) {
  const isUser = role === "user";
  const row = document.createElement("div");
  row.className = `msg ${isUser ? "user" : "assistant"}`;
  const avatar = isUser ? "👤" : "🤖";
  const bubbleContent = isUser ? escapeHtml(content) : renderMarkdown(content);
  row.innerHTML = `
    <div class="avatar">${avatar}</div>
    <div class="bubble">${bubbleContent}</div>
  `;
  messagesEl.appendChild(row);

  if (!isUser && sources && sources.length) {
    messagesEl.appendChild(buildSourcesBlock(sources));
  }
  scrollToBottom();
  refreshIcons();
}

function buildSourcesBlock(sources) {
  const wrap = document.createElement("div");
  wrap.className = "sources";
  wrap.innerHTML = `<h3>Sources (${sources.length})</h3>`;
  sources.forEach((s, i) => {
    const a = document.createElement("a");
    a.className = "source";
    a.href = s.url || "#";
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.innerHTML = `
      <div class="source-title">[${i + 1}] ${escapeHtml(s.title || "Untitled")}</div>
      <div class="source-url">${escapeHtml(s.url || "")}</div>
    `;
    wrap.appendChild(a);
  });
  return wrap;
}

/* ---------- Progress UI ---------- */
function createProgressBlock() {
  const el = document.createElement("div");
  el.className = "progress loading";
  el.id = "live-progress";
  renderAILoader(el);
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function addStep(block, icon, text, state = "run") {
  const step = document.createElement("div");
  step.className = "progress-step " + (state === "done" ? "done" : "");
  const marker =
    state === "done"
      ? `<span class="check">✓</span>`
      : state === "warn"
      ? `<span class="warn">⚠</span>`
      : `<span class="spinner"></span>`;
  step.innerHTML = `${marker}<span>${text}</span>`;
  block.appendChild(step);
  scrollToBottom();
  return step;
}

function markStepDone(step, text) {
  if (!step) return;
  step.classList.add("done");
  step.innerHTML = `<span class="check">✓</span><span>${text}</span>`;
}

function clearProgress() {
  const el = document.getElementById("live-progress");
  if (el) el.remove();
}

/* ============================================================
   SEND MESSAGE — SSE streaming with DB polling fallback
   ============================================================ */
async function sendMessage(text) {
  text = (text || "").trim();
  if (!text) return;

  hideWelcome();
  appendMessage("user", text, []);
  input.value = "";
  input.style.height = "auto";

  const progress = createProgressBlock();
  let planningStep = addStep(progress, "spinner", "🤔 Understanding question…");

  sendBtn.classList.add("hidden");
  stopBtn.classList.remove("hidden");
  setStatus("Researching…", "#f59e0b");

  currentController = new AbortController();

  let finalReport = "";
  let finalSources = [];
  let newChatId = null;
  let sseCompleted = false;

  try {
    const res = await fetch(API.research, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: activeChatId, message: text }),
      signal: currentController.signal,
    });

    if (!res.ok || !res.body) {
      const errText = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status} ${errText.slice(0, 200)}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = null;
    let dataLines = [];

    let searchStep = null;
    let evalStep = null;
    let followupStep = null;
    let writeStep = null;

    const dispatch = (event, data) => {
      let payload = {};
      try { payload = JSON.parse(data); } catch {}
      console.log(">>> SSE", event, payload);

      // Once a real step arrives, retire the AI loader and show the step list.
      const lp = document.getElementById("live-progress");
      if (lp && lp.classList.contains("loading")) {
        lp.classList.remove("loading");
        lp.innerHTML = "";
        planningStep = addStep(lp, "spinner", "🤔 Understanding question…");
      }

      switch (event) {
        case "research_started":
          newChatId = payload.chat_id;
          markStepDone(planningStep, "🤔 Question received");
          planningStep = addStep(progress, "spinner", "📋 Planning research queries…");
          break;

        case "planning": {
          markStepDone(planningStep, "📋 Research plan created");
          (payload.queries || []).forEach((q, i) => {
            addStep(progress, "spinner", `&nbsp;&nbsp;· Query ${i + 1}: ${escapeHtml(q)}`, "done");
          });
          searchStep = addStep(progress, "spinner", "🔎 Searching the web…");
          break;
        }

        case "search_completed": {
          const total = payload.total_sources ?? 0;
          if (searchStep) markStepDone(searchStep, `🔎 Web search complete (${total} sources so far)`);
          searchStep = addStep(progress, "spinner", "🌐 Collecting sources…");
          break;
        }

        case "sources_collected": {
          if (searchStep) markStepDone(searchStep, `📚 Sources collected (${payload.total_sources ?? 0})`);
          evalStep = addStep(progress, "spinner", "🧠 Evaluating evidence…");
          break;
        }

        case "evaluation_completed": {
          const ok = payload.is_sufficient;
          if (evalStep) markStepDone(evalStep, ok ? "🧠 Evidence sufficient" : "🧠 Evidence insufficient");
          if (ok) writeStep = addStep(progress, "spinner", "✍️ Writing final answer…");
          break;
        }

        case "followup_search": {
          if (evalStep) markStepDone(evalStep, "⚠ Information gap detected");
          (payload.next_queries || []).forEach((q) =>
            addStep(progress, "spinner", `&nbsp;&nbsp;· Follow-up: ${escapeHtml(q)}`, "done")
          );
          followupStep = addStep(progress, "spinner", "🔎 Performing follow-up search…");
          break;
        }

        case "writing_started":
          if (followupStep) markStepDone(followupStep, "✓ Additional evidence collected");
          if (!writeStep) writeStep = addStep(progress, "spinner", "✍️ Writing final answer…");
          setStatus("Writing report… (30-60s)", "#f59e0b");
          break;

        case "research_completed": {
          if (payload.report_b64) {
            try {
              const bin = atob(payload.report_b64);
              const bytes = new Uint8Array(bin.length);
              for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
              finalReport = new TextDecoder("utf-8").decode(bytes);
            } catch (e) {
              console.error("Base64 decode failed:", e);
              finalReport = payload.report || "";
            }
          } else {
            finalReport = payload.report || "";
          }
          finalSources = payload.sources || [];
          newChatId = payload.chat_id || newChatId;
          if (writeStep) markStepDone(writeStep, "✓ Research completed");
          setStatus("Ready", "#10b981");
          sseCompleted = true;
          break;
        }

        case "error":
          addStep(progress, "warn", `❌ Error: ${escapeHtml(payload.message || "unknown")}`, "warn");
          setStatus("Error", "#ef4444");
          break;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        currentEvent = null;
        dataLines = [];

        raw.split("\n").forEach((line) => {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            let value = line.slice(5);
            if (value.startsWith(" ")) value = value.slice(1);
            dataLines.push(value);
          }
        });

        if (currentEvent && dataLines.length) {
          dispatch(currentEvent, dataLines.join("\n"));
        }
      }
    }
  } catch (err) {
    console.warn("SSE stream ended:", err.name || err.message);
  }

  /* ---------- POLLING FALLBACK ---------- */
  if (!sseCompleted && (!finalReport || !finalReport.trim()) && newChatId) {
    console.log("SSE incomplete — polling DB for report...");
    setStatus("Waiting for agent (polling)...", "#f59e0b");

    const MAX_WAIT_MS = 10 * 60 * 1000;
    const startedAt = Date.now();
    let delay = 2000;

    while (Date.now() - startedAt < MAX_WAIT_MS) {
      await new Promise(r => setTimeout(r, delay));
      delay = Math.min(delay * 1.2, 6000);

      try {
        const r = await fetch(API.messages(newChatId));
        const msgs = await r.json();
        const lastAssistant = [...msgs].reverse().find(m => m.role === "assistant");
        if (
          lastAssistant &&
          lastAssistant.content &&
          lastAssistant.content.trim().length > 20
        ) {
          finalReport = lastAssistant.content;
          finalSources = lastAssistant.sources || [];
          break;
        }
      } catch (e) {
        console.warn("Poll failed:", e);
      }
    }
  }

  /* ---------- FINAL RENDER ---------- */
  clearProgress();

  if (finalReport && finalReport.trim()) {
    appendMessage("assistant", finalReport, finalSources);
    setStatus("Ready", "#10b981");
  } else {
    appendMessage("assistant", "_Research did not complete within 10 minutes. Please try again._", []);
    setStatus("Error", "#ef4444");
  }

  if (newChatId) {
    if (!activeChatId) activeChatId = newChatId;
    loadChats();
  }

  sendBtn.classList.remove("hidden");
  stopBtn.classList.add("hidden");
  currentController = null;
  refreshIcons();
}

/* ---------- Events ---------- */
if (form) {
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(input.value);
  });
}

if (input) {
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 150) + "px";
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (form) form.requestSubmit();
    }
  });
}

if (newChatBtn) {
  newChatBtn.addEventListener("click", () => {
    activeChatId = null;
    showWelcome();
    loadChats();
    if (window.innerWidth <= 780 && sidebar) sidebar.classList.remove("open");
  });
}

if (stopBtn) {
  stopBtn.addEventListener("click", () => {
    if (currentController) currentController.abort();
  });
}

/* ---------- Mobile menu toggle ---------- */
if (menuToggle && sidebar) {
  const checkMobile = () => {
    if (window.innerWidth <= 780) {
      menuToggle.classList.remove("hidden");
    } else {
      menuToggle.classList.add("hidden");
      sidebar.classList.remove("open");
    }
  };
  window.addEventListener("resize", checkMobile);
  checkMobile();

  menuToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
  });
}

/* ---------- Suggestion chips ---------- */
document.querySelectorAll(".suggestion").forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.dataset.q || btn.textContent.trim();
    if (input) input.value = q;
    sendMessage(q);
  });
});

/* ---------- Feature cards ---------- */
document.querySelectorAll(".feature-card").forEach((card) => {
  card.addEventListener("click", () => {
    const q = card.dataset.q || card.querySelector("h3")?.textContent || "";
    if (input) input.value = q;
    sendMessage(q);
  });
});

/* ---------- Nav items ---------- */
document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((i) => i.classList.remove("active"));
    item.classList.add("active");
  });
});

/* ---------- Boot ---------- */
window.addEventListener("DOMContentLoaded", () => {
  refreshIcons();
  loadChats();
  if (input) input.focus();
});

window.addEventListener("load", refreshIcons);