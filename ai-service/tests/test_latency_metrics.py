from livekit.agents.metrics import EOUMetrics, TTSMetrics

from app.voice_agent.latency_metrics import _MAX_PENDING, SpeechToSpeechCorrelator


def _eou(speech_id: str, timestamp: float) -> EOUMetrics:
    return EOUMetrics(
        timestamp=timestamp,
        end_of_utterance_delay=0.1,
        transcription_delay=0.05,
        on_user_turn_completed_delay=0.02,
        speech_id=speech_id,
    )


def _tts(speech_id: str, timestamp: float, ttfb: float) -> TTSMetrics:
    return TTSMetrics(
        label="test",
        request_id="req-1",
        timestamp=timestamp,
        ttfb=ttfb,
        duration=1.0,
        audio_duration=1.0,
        cancelled=False,
        characters_count=10,
        streamed=True,
        speech_id=speech_id,
    )


def test_matching_speech_id_logs_composite_metric(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(
        "app.voice_agent.latency_metrics.append_agent_metric", lambda record: logged.append(record)
    )
    correlator = SpeechToSpeechCorrelator()
    correlator.on_eou(_eou("s1", timestamp=100.0))
    correlator.on_tts(_tts("s1", timestamp=100.5, ttfb=0.4))

    assert len(logged) == 1
    assert logged[0]["type"] == "speech_to_speech"
    assert logged[0]["speech_id"] == "s1"
    assert logged[0]["speech_to_speech_s"] == 0.9


def test_tts_with_no_matching_eou_is_a_noop(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(
        "app.voice_agent.latency_metrics.append_agent_metric", lambda record: logged.append(record)
    )
    correlator = SpeechToSpeechCorrelator()
    correlator.on_tts(_tts("unknown", timestamp=100.0, ttfb=0.2))
    assert logged == []


def test_eou_is_consumed_on_matching_tts(monkeypatch) -> None:
    logged = []
    monkeypatch.setattr(
        "app.voice_agent.latency_metrics.append_agent_metric", lambda record: logged.append(record)
    )
    correlator = SpeechToSpeechCorrelator()
    correlator.on_eou(_eou("s1", timestamp=100.0))
    correlator.on_tts(_tts("s1", timestamp=100.5, ttfb=0.4))
    correlator.on_tts(_tts("s1", timestamp=200.0, ttfb=0.1))  # duplicate/stale, already consumed

    assert len(logged) == 1


def test_cache_evicts_oldest_once_full() -> None:
    correlator = SpeechToSpeechCorrelator()
    for i in range(_MAX_PENDING + 5):
        correlator.on_eou(_eou(f"s{i}", timestamp=float(i)))

    assert len(correlator._pending_eou_ts) == _MAX_PENDING
    assert "s0" not in correlator._pending_eou_ts
    assert f"s{_MAX_PENDING + 4}" in correlator._pending_eou_ts
