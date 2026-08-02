"""
Dev-only live view of model_gateway's per-turn metrics (see
model_gateway/gateway.py's _log_metrics and metrics_log.py), the voice
agent's own STT/TTS/turn-detection metrics (see voice_agent/dev_metrics.py),
and a live transcript snapshot (see voice_agent/gateway_llm.py). Not a
product feature — no auth, no tenant scoping, reads local files. Do not
expose this router outside local development.

Live updates ride a single WebSocket connection (see metrics_ws.py) instead
of polling on a timer — a plain "refetch every 1.5s" approach has no way to
know "nothing is running right now," so it keeps firing requests forever
even with no interview active. The WS watcher only does anything (and only
sends anything) when there's a connected client *and* genuinely new data;
REST endpoints below still exist for the one-time initial page load, a
catch-up fetch after reconnecting, and the on-demand context-detail fetch
(a row's full content is only loaded when actually clicked).
"""

# ruff: noqa: E501 — the embedded HTML/CSS/JS template below isn't Python
# source; wrapping markup/CSS declarations at 100 cols hurts readability
# more than it helps.

from fastapi import APIRouter, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

from ..model_gateway.metrics_log import (
    find_metric_by_ts,
    read_recent,
    read_recent_agent_metrics,
    read_transcript_snapshot,
    slim_llm_record,
)
from .metrics_ws import metrics_websocket_endpoint

router = APIRouter(prefix="/dev/metrics", tags=["dev-tools"])

_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Model Gateway — Live Metrics & Prompt History</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: ui-monospace, "SF Mono", Consolas, monospace; margin: 0; padding: 24px;
         background: #0b0f14; color: #d8e0e8; }
  h1 { font-size: 16px; font-weight: 600; margin: 0 0 4px; color: #8fb8ff; }
  .sub { color: #6b7785; font-size: 12px; margin-bottom: 16px; }
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid #1c2530; }
  .tab { padding: 8px 14px; font-size: 13px; cursor: pointer; color: #6b7785; border-bottom: 2px solid transparent; }
  .tab.active { color: #8fb8ff; border-bottom-color: #8fb8ff; }
  .panel { display: none; }
  .panel.active { display: block; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #1c2530; white-space: nowrap; }
  th { color: #6b7785; font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em; }
  tr.row:hover td { background: #111a24; cursor: pointer; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .p-groq { background: #1f3a2e; color: #6fe3a0; }
  .p-gemini { background: #2a2f57; color: #9db2ff; }
  .p-openrouter { background: #4a2f1f; color: #ffb774; }
  .p-openai { background: #1f3a4a; color: #74d4ff; }
  .uc-badge { display: inline-block; padding: 1px 8px; border-radius: 6px; font-size: 11px; font-weight: 500; font-family: monospace; }
  .uc-voice_interview_turn { background: #1a2736; color: #8fb8ff; border: 1px solid #2d4263; }
  .uc-voice_interview_summary { background: #2b2518; color: #ffd166; border: 1px solid #5c4720; }
  .uc-role_discovery_turn { background: #1f332b; color: #06d6a0; border: 1px solid #236952; }
  .uc-role_discovery_extraction { background: #2d1e36; color: #ef476f; border: 1px solid #592d6b; }
  .search-bar { display: flex; gap: 10px; margin-bottom: 12px; align-items: center; }
  .search-input { background: #111a24; border: 1px solid #1c2530; color: #d8e0e8; padding: 6px 12px; border-radius: 6px; font-size: 13px; width: 340px; }
  .search-input:focus { outline: none; border-color: #8fb8ff; }
  .t-stt_metrics { background: #2a2f57; color: #9db2ff; }
  .t-tts_metrics { background: #1f3a2e; color: #6fe3a0; }
  .t-eou_metrics { background: #4a2f1f; color: #ffb774; }
  .t-vad_metrics { background: #3a1f4a; color: #d19bff; }
  .t-speech_to_speech { background: #1f4a3a; color: #6fe3c9; }
  .fallback { color: #ff8a8a; font-weight: 600; }
  .interrupted { color: #ffcf6b; }
  .ttft-good { color: #6fe3a0; }
  .ttft-warn { color: #ffcf6b; }
  .ttft-bad { color: #ff8a8a; }
  .empty { color: #6b7785; padding: 40px 0; text-align: center; }
  .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #6fe3a0;
         margin-right: 6px; animation: pulse 1.5s ease-in-out infinite; }
  .dot.paused { background: #6b7785; animation: none; }
  .dot.error { background: #ff8a8a; animation: none; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
  .detail-row td { background: #0e141b; padding: 16px 20px; white-space: normal; }
  .detail-block { margin-bottom: 14px; }
  .detail-label { color: #8fb8ff; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
  .detail-code { background: #070b0f; border: 1px solid #1c2530; border-radius: 6px; padding: 12px 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 380px; overflow-y: auto; line-height: 1.5; margin-top: 4px; }
  .prompt-system { border-left: 3px solid #8fb8ff; color: #c8d8f8; }
  .prompt-user { border-left: 3px solid #ffb774; color: #f8e0c8; }
  .prompt-output { border-left: 3px solid #6fe3a0; color: #d0f8e0; background: #071510; }
  .detail-lines { white-space: pre-wrap; line-height: 1.5; color: #c3ccd4; background: #090d12; padding: 10px 12px; border-radius: 6px; border: 1px solid #18222d; }
  .detail-summary { white-space: pre-wrap; line-height: 1.5; color: #ffcf6b; background: #14110b; padding: 10px 12px; border-radius: 6px; border: 1px solid #2d2415; }
  .bubbles { display: flex; flex-direction: column; gap: 10px; max-width: 720px; }
  .bubble { padding: 8px 14px; border-radius: 12px; font-size: 13px; line-height: 1.4; max-width: 80%; }
  .bubble.candidate { align-self: flex-start; background: #1c2530; color: #d8e0e8; }
  .bubble.interviewer { align-self: flex-end; background: #1f3a4a; color: #bfe6ff; }
  .bubble .who { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em;
                 opacity: 0.6; margin-bottom: 3px; }
</style>
</head>
<body>
  <h1><span class="dot" id="live-dot"></span>Model Gateway — Live Metrics & Prompt History</h1>
  <div class="sub" id="status-line">Connecting…</div>

  <div class="tabs">
    <div class="tab active" data-tab="llm">LLM Calls</div>
    <div class="tab" data-tab="agent">STT / TTS / Turn Detection</div>
    <div class="tab" data-tab="transcript">Live Transcript</div>
  </div>

  <div class="panel active" id="panel-llm">
    <div class="search-bar">
      <input type="text" id="llm-search" class="search-input" placeholder="Search calls (use case, model, prompt text)..." oninput="filterLlmRows()">
      <span class="sub" id="llm-count-label" style="margin-bottom:0;"></span>
    </div>
    <table>
      <thead>
        <tr>
          <th></th><th>Time</th><th>Use case</th><th>Provider</th><th>Model</th>
          <th>Context (tok≈)</th><th>Output</th><th>TTFT</th><th>Total latency</th><th>Flags</th>
        </tr>
      </thead>
      <tbody id="llm-rows"><tr><td colspan="10" class="empty">Waiting for interview activity…</td></tr></tbody>
    </table>
  </div>

  <div class="panel" id="panel-agent">
    <table>
      <thead>
        <tr><th>Time</th><th>Type</th><th>Label</th><th>Key timings</th></tr>
      </thead>
      <tbody id="agent-rows"><tr><td colspan="4" class="empty">Waiting for interview activity…</td></tr></tbody>
    </table>
  </div>

  <div class="panel" id="panel-transcript">
    <div class="sub" id="transcript-session"></div>
    <div class="bubbles" id="transcript-bubbles"><div class="empty">No transcript yet.</div></div>
  </div>

<script>
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("panel-" + tab.dataset.tab).classList.add("active");
  });
});

function fmtTime(ts) { return new Date(ts * 1000).toLocaleTimeString(); }
function ttftClass(v) {
  if (v == null) return "";
  if (v < 1.0) return "ttft-good";
  if (v < 2.5) return "ttft-warn";
  return "ttft-bad";
}
function esc(s) {
  return (s ?? "").toString().replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
}

let llmRowSeq = 0;
let lastLlmTs = 0;
let lastAgentTs = 0;
let lastTranscriptUpdatedAt = null;

async function fetchDetail(ts, targetEl) {
  targetEl.innerHTML = '<div class="empty">Loading context & prompt details…</div>';
  try {
    const res = await fetch(`/dev/metrics/data/detail?ts=${ts}`);
    const d = await res.json();
    if (!d) { targetEl.innerHTML = '<div class="empty">No context detail captured for this turn.</div>'; return; }
    
    let html = '';
    if (d.session) {
      html += `
        <div class="detail-block">
          <div class="detail-label">Session ID</div>
          <div style="font-size:12px; color:#8fb8ff;">${esc(d.session)}</div>
        </div>
      `;
    }
    
    if (d.system_prompt) {
      html += `
        <div class="detail-block">
          <div class="detail-label">System Prompt (${d.system_prompt.length} chars)</div>
          <div class="detail-code prompt-system">${esc(d.system_prompt)}</div>
        </div>
      `;
    }
    
    if (d.user_prompt) {
      html += `
        <div class="detail-block">
          <div class="detail-label">User Prompt (${d.user_prompt.length} chars)</div>
          <div class="detail-code prompt-user">${esc(d.user_prompt)}</div>
        </div>
      `;
    }
    
    if (d.output_text) {
      html += `
        <div class="detail-block">
          <div class="detail-label">LLM Generated Response (${d.output_text.length} chars)</div>
          <div class="detail-code prompt-output">${esc(d.output_text)}</div>
        </div>
      `;
    }

    if (d.recent_window_lines && d.recent_window_lines.length > 0) {
      const lines = d.recent_window_lines.map(esc).join("\\n");
      html += `
        <div class="detail-block">
          <div class="detail-label">Recent Conversation Window (${d.recent_window_lines.length} lines)</div>
          <div class="detail-lines">${lines}</div>
        </div>
      `;
    }

    if (d.summary) {
      html += `
        <div class="detail-block">
          <div class="detail-label">Rolling Summary (covers ${d.summarized_line_count || 0} earlier lines)</div>
          <div class="detail-summary">${esc(d.summary)}</div>
        </div>
      `;
    }

    targetEl.innerHTML = html || '<div class="empty">No prompt or context details available.</div>';
  } catch (e) {
    targetEl.innerHTML = '<div class="empty">Failed to load detail.</div>';
  }
}

function filterLlmRows() {
  const q = (document.getElementById("llm-search")?.value || "").toLowerCase();
  let count = 0;
  document.querySelectorAll("#llm-rows tr.row").forEach(tr => {
    const text = tr.textContent.toLowerCase();
    const rowId = tr.dataset.rowId;
    const detailRow = document.querySelector(`tr[data-detail-for="${rowId}"]`);
    if (!q || text.includes(q)) {
      tr.style.display = "table-row";
      count++;
    } else {
      tr.style.display = "none";
      if (detailRow) detailRow.style.display = "none";
    }
  });
  const label = document.getElementById("llm-count-label");
  if (label) label.textContent = q ? `${count} matching call(s)` : "";
}

function ucBadgeClass(uc) {
  if (!uc) return "uc-badge";
  return `uc-badge uc-${esc(uc)}`;
}

function llmRowHtml(r, rowId) {
  const flags = [];
  if (r.used_fallback) flags.push('<span class="fallback">FALLBACK</span>');
  if (r.interrupted) flags.push('<span class="interrupted">INTERRUPTED</span>');
  const arrow = r.has_detail ? "▸" : "";
  return `<tr class="row" data-row-id="${rowId}" data-ts="${r.ts}" data-has-detail="${!!r.has_detail}">
    <td>${arrow}</td>
    <td>${fmtTime(r.ts)}</td>
    <td><span class="${ucBadgeClass(r.use_case)}">${esc(r.use_case)}</span></td>
    <td><span class="badge p-${esc(r.provider)}">${esc(r.provider)}</span></td>
    <td>${esc(r.model) || "-"}</td>
    <td>${r.approx_context_tokens}</td>
    <td>${r.output_chars}</td>
    <td class="${ttftClass(r.ttft_s)}">${r.ttft_s != null ? r.ttft_s.toFixed(2) + "s" : "-"}</td>
    <td>${r.latency_s.toFixed(2)}s</td>
    <td>${flags.join(" ")}</td>
  </tr>
  <tr class="detail-row" data-detail-for="${rowId}" style="display:none"><td colspan="10"></td></tr>`;
}

function bindRowClick(tr) {
  tr.addEventListener("click", () => {
    if (tr.dataset.hasDetail !== "true") return;
    const rowId = tr.dataset.rowId;
    const detailRow = document.querySelector(`tr[data-detail-for="${rowId}"]`);
    const cell = detailRow.querySelector("td");
    const isOpen = detailRow.style.display !== "none";
    document.querySelectorAll("#llm-rows tr.detail-row").forEach(d => d.style.display = "none");
    if (isOpen) return;
    detailRow.style.display = "table-row";
    fetchDetail(tr.dataset.ts, cell);
  });
}

function addLlmRow(r) {
  const tbody = document.getElementById("llm-rows");
  if (tbody.querySelector(".empty")) tbody.innerHTML = "";
  const rowId = ++llmRowSeq;
  tbody.insertAdjacentHTML("afterbegin", llmRowHtml(r, rowId));
  bindRowClick(tbody.querySelector(`tr[data-row-id="${rowId}"]`));
  lastLlmTs = Math.max(lastLlmTs, r.ts);
  filterLlmRows();
}

function agentKeyTimings(r) {
  switch (r.type) {
    case "stt_metrics":
      return `audio=${(r.audio_duration ?? 0).toFixed(2)}s · req=${(r.duration ?? 0).toFixed(2)}s · streamed=${r.streamed}`;
    case "tts_metrics":
      return `ttfb=${(r.ttfb ?? 0).toFixed(2)}s · total=${(r.duration ?? 0).toFixed(2)}s · audio=${(r.audio_duration ?? 0).toFixed(2)}s · chars=${r.characters_count}`;
    case "eou_metrics":
      return `eou_delay=${(r.end_of_utterance_delay ?? 0).toFixed(2)}s · transcription=${(r.transcription_delay ?? 0).toFixed(2)}s`;
    case "vad_metrics":
      return `idle=${(r.idle_time ?? 0).toFixed(2)}s · inferences=${r.inference_count}`;
    case "speech_to_speech":
      return `speech→speech=${(r.speech_to_speech_s ?? 0).toFixed(2)}s`;
    default:
      return "-";
  }
}

function agentBadgeLabel(type) {
  return type === "speech_to_speech" ? "s2s" : type.replace("_metrics", "");
}

function addAgentRow(r) {
  const tbody = document.getElementById("agent-rows");
  if (tbody.querySelector(".empty")) tbody.innerHTML = "";
  tbody.insertAdjacentHTML("afterbegin", `<tr>
    <td>${fmtTime(r.ts)}</td>
    <td><span class="badge t-${esc(r.type)}">${esc(agentBadgeLabel(r.type))}</span></td>
    <td>${esc(r.label) || "-"}</td>
    <td>${agentKeyTimings(r)}</td>
  </tr>`);
  lastAgentTs = Math.max(lastAgentTs, r.ts);
}

function renderTranscript(data) {
  if (!data || !data.lines || data.lines.length === 0) return;
  if (data.updated_at === lastTranscriptUpdatedAt) return; // no-op, skip re-render
  lastTranscriptUpdatedAt = data.updated_at;
  const container = document.getElementById("transcript-bubbles");
  const sessionLabel = document.getElementById("transcript-session");
  sessionLabel.textContent = `Session: ${data.session} · updated ${fmtTime(data.updated_at)}`;
  container.innerHTML = data.lines.map(line => {
    const isCandidate = line.startsWith("Candidate:");
    const who = isCandidate ? "Candidate" : "Interviewer";
    const text = line.replace(/^(Candidate|Interviewer):\\s*/, "");
    return `<div class="bubble ${isCandidate ? "candidate" : "interviewer"}"><span class="who">${who}</span>${esc(text)}</div>`;
  }).join("");
}

async function initialLoad() {
  try {
    const [llmRes, agentRes, transcriptRes] = await Promise.all([
      fetch(`/dev/metrics/data?after_ts=${lastLlmTs}`),
      fetch(`/dev/metrics/agent-data?after_ts=${lastAgentTs}`),
      fetch("/dev/metrics/transcript"),
    ]);
    for (const r of (await llmRes.json())) addLlmRow(r);
    for (const r of (await agentRes.json())) addAgentRow(r);
    renderTranscript(await transcriptRes.json());
  } catch (e) { /* dashboard will just stay empty until WS connects */ }
}

function setStatus(text, dotClass) {
  document.getElementById("status-line").textContent = text;
  const dot = document.getElementById("live-dot");
  dot.classList.remove("paused", "error");
  if (dotClass) dot.classList.add(dotClass);
}

let ws = null;
let reconnectDelayMs = 1000;

function connectWs() {
  if (ws) return;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/dev/metrics/ws`);

  ws.onopen = () => {
    reconnectDelayMs = 1000;
    setStatus("Live — connected", null);
    // Catch-up: pick up anything written while we were disconnected/hidden.
    initialLoad();
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "llm") addLlmRow(msg.record);
    else if (msg.type === "agent") addAgentRow(msg.record);
    else if (msg.type === "transcript") renderTranscript(msg.snapshot);
  };
  ws.onclose = () => {
    ws = null;
    if (document.hidden) { setStatus("Paused (tab hidden)", "paused"); return; }
    setStatus("Reconnecting…", "error");
    setTimeout(connectWs, reconnectDelayMs);
    reconnectDelayMs = Math.min(reconnectDelayMs * 2, 15000);
  };
  ws.onerror = () => ws.close();
}

function disconnectWs() {
  if (!ws) return;
  ws.onclose = null; // don't trigger the reconnect-on-close path for a deliberate disconnect
  ws.close();
  ws = null;
  setStatus("Paused (tab hidden)", "paused");
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) disconnectWs(); else connectWs();
});

initialLoad().then(() => { if (!document.hidden) connectWs(); });
</script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
async def dashboard() -> str:
    return _PAGE


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await metrics_websocket_endpoint(ws)


@router.get("/data")
async def data(after_ts: float = 0) -> JSONResponse:
    records = read_recent(limit=200, after_ts=after_ts or None)
    return JSONResponse([slim_llm_record(r) for r in records])


@router.get("/data/detail")
async def data_detail(ts: float) -> JSONResponse:
    record = find_metric_by_ts(ts)
    return JSONResponse(record.get("context_detail") if record else None)


@router.get("/agent-data")
async def agent_data(after_ts: float = 0) -> JSONResponse:
    return JSONResponse(read_recent_agent_metrics(limit=200, after_ts=after_ts or None))


@router.get("/transcript")
async def transcript() -> JSONResponse:
    return JSONResponse(read_transcript_snapshot())
