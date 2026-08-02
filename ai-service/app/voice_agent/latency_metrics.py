"""Correlates two framework-emitted metrics that today land as separate,
uncorrelated events (see dev_metrics.py) into one composite number: how long
from "the candidate stopped talking" to "the agent's reply started playing."
That's what a candidate actually perceives as response latency — total LLM
latency or TTFT alone don't capture it, since they start the clock only once
the LLM call itself begins, not from the moment the candidate finished
speaking.

EOUMetrics and TTSMetrics both carry a shared `speech_id` (confirmed against
the installed livekit-agents==1.6.7 metrics dataclasses) — the correlation
key used below. EOUMetrics.timestamp marks end-of-utterance detection;
TTSMetrics.timestamp + TTSMetrics.ttfb marks when the first audio byte was
produced for that turn's reply.

Dev-only, gated the same way as every other metric in this module's sibling
dev_metrics.py — see is_dev_metrics_enabled()."""

from livekit.agents.metrics import EOUMetrics, TTSMetrics

from ..model_gateway.metrics_log import append_agent_metric

# Bounds memory for a long-running interview — a turn's EOU and its TTS
# reply arrive close together in practice, so this is generous headroom,
# not a tight budget. Oldest entries are evicted first once the cache is full.
_MAX_PENDING = 20


class SpeechToSpeechCorrelator:
    def __init__(self) -> None:
        self._pending_eou_ts: dict[str, float] = {}

    def on_eou(self, metrics: EOUMetrics) -> None:
        if metrics.speech_id is None:
            return
        if len(self._pending_eou_ts) >= _MAX_PENDING:
            oldest_speech_id = next(iter(self._pending_eou_ts))
            del self._pending_eou_ts[oldest_speech_id]
        self._pending_eou_ts[metrics.speech_id] = metrics.timestamp

    def on_tts(self, metrics: TTSMetrics) -> None:
        if metrics.speech_id is None:
            return
        eou_ts = self._pending_eou_ts.pop(metrics.speech_id, None)
        if eou_ts is None:
            return
        speech_to_speech_s = (metrics.timestamp + metrics.ttfb) - eou_ts
        append_agent_metric(
            {
                "type": "speech_to_speech",
                "speech_id": metrics.speech_id,
                "speech_to_speech_s": round(speech_to_speech_s, 3),
            }
        )
