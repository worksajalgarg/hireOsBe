"""Dev-only bridge from livekit-agents' own metrics_collected event into the
dashboard's log files (see model_gateway/metrics_log.py). AgentSession
already emits STTMetrics/TTSMetrics/EOUMetrics/VADMetrics/LLMMetrics for
every STT/TTS/turn-detection/LLM call it makes (see agent_activity.py in the
installed livekit-agents package) — this just captures them instead of
re-instrumenting the Deepgram/ElevenLabs plugin calls ourselves.

LLM metrics are deliberately skipped: GatewayLLM's actual provider varies
turn-to-turn (Groq primary, Gemini fallback — see gateway_llm.py), which
this generic event can't reflect. model_gateway/gateway.py's own metrics
log already has the accurate per-turn provider/model, so capturing the
framework's LLM metrics here would just be a second, less accurate copy.

Gated behind DEV_METRICS_ENABLED (default off): this whole subsystem writes
to a local file and (via gateway_llm.py's context_detail/transcript
snapshot) can include raw candidate/interviewer speech content. That's fine
for a developer running the worker locally, but it must never turn on by
accident in a real deployment — it bypasses the encrypted-object-storage /
audit-trail path that real candidate data goes through (see
hireOsBe/CLAUDE.md), and assumes the worker and dashboard share a local
filesystem, which is only true on one dev machine.
"""

import os

from livekit.agents.voice import AgentSession, MetricsCollectedEvent

from ..model_gateway.metrics_log import append_agent_metric

_CAPTURED_TYPES = {"stt_metrics", "tts_metrics", "eou_metrics", "vad_metrics"}


def is_dev_metrics_enabled() -> bool:
    return os.environ.get("DEV_METRICS_ENABLED", "false").strip().lower() == "true"


def register_dev_metrics_listener(session: AgentSession, session_label: str) -> None:
    def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        if ev.metrics.type not in _CAPTURED_TYPES:
            return
        append_agent_metric({"session": session_label, **ev.metrics.model_dump()})

    session.on("metrics_collected", _on_metrics_collected)
