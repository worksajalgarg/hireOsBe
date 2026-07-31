"""
Dev-only live view of model_gateway's per-turn metrics (see
model_gateway/gateway.py's _log_metrics and metrics_log.py). Not a product
feature — no auth, no tenant scoping, reads a local JSON-lines file. Do not
expose this router outside local development.
"""

# ruff: noqa: E501 — the embedded HTML/CSS/JS template below isn't Python
# source; wrapping markup/CSS declarations at 100 cols hurts readability
# more than it helps.

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from ..model_gateway.metrics_log import read_recent

router = APIRouter(prefix="/dev/metrics", tags=["dev-tools"])

_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Model Gateway — Live Metrics</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: ui-monospace, "SF Mono", Consolas, monospace; margin: 0; padding: 24px;
         background: #0b0f14; color: #d8e0e8; }
  h1 { font-size: 16px; font-weight: 600; margin: 0 0 4px; color: #8fb8ff; }
  .sub { color: #6b7785; font-size: 12px; margin-bottom: 18px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #1c2530; white-space: nowrap; }
  th { color: #6b7785; font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em; }
  tr:hover td { background: #111a24; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .p-groq { background: #1f3a2e; color: #6fe3a0; }
  .p-gemini { background: #2a2f57; color: #9db2ff; }
  .p-openrouter { background: #4a2f1f; color: #ffb774; }
  .p-openai { background: #1f3a4a; color: #74d4ff; }
  .fallback { color: #ff8a8a; font-weight: 600; }
  .interrupted { color: #ffcf6b; }
  .ttft-good { color: #6fe3a0; }
  .ttft-warn { color: #ffcf6b; }
  .ttft-bad { color: #ff8a8a; }
  .empty { color: #6b7785; padding: 40px 0; text-align: center; }
  .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #6fe3a0;
         margin-right: 6px; animation: pulse 1.5s ease-in-out infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
</style>
</head>
<body>
  <h1><span class="dot"></span>Model Gateway — Live Metrics</h1>
  <div class="sub">Auto-refreshes every 1.5s · newest first · dev-only, not a product feature</div>
  <table>
    <thead>
      <tr>
        <th>Time</th><th>Use case</th><th>Provider</th><th>Model</th>
        <th>Context (tok≈)</th><th>Output (chars)</th><th>TTFT</th><th>Total latency</th><th>Flags</th>
      </tr>
    </thead>
    <tbody id="rows"><tr><td colspan="9" class="empty">Waiting for interview activity…</td></tr></tbody>
  </table>

<script>
function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}
function ttftClass(v) {
  if (v == null) return "";
  if (v < 1.0) return "ttft-good";
  if (v < 2.5) return "ttft-warn";
  return "ttft-bad";
}
async function refresh() {
  try {
    const res = await fetch("/dev/metrics/data");
    const data = await res.json();
    const rows = data.slice().reverse();
    const tbody = document.getElementById("rows");
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">Waiting for interview activity…</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const flags = [];
      if (r.used_fallback) flags.push('<span class="fallback">FALLBACK</span>');
      if (r.interrupted) flags.push('<span class="interrupted">INTERRUPTED</span>');
      return `<tr>
        <td>${fmtTime(r.ts)}</td>
        <td>${r.use_case}</td>
        <td><span class="badge p-${r.provider}">${r.provider}</span></td>
        <td>${r.model || "-"}</td>
        <td>${r.approx_context_tokens}</td>
        <td>${r.output_chars}</td>
        <td class="${ttftClass(r.ttft_s)}">${r.ttft_s != null ? r.ttft_s.toFixed(2) + "s" : "-"}</td>
        <td>${r.latency_s.toFixed(2)}s</td>
        <td>${flags.join(" ")}</td>
      </tr>`;
    }).join("");
  } catch (e) { /* server not up yet — keep polling silently */ }
}
refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
async def dashboard() -> str:
    return _PAGE


@router.get("/data")
async def data() -> JSONResponse:
    return JSONResponse(read_recent(limit=200))
