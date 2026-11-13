"""LiteLLM callback: Prometheus counters for audio transcription speed (audio seconds, words, processing time)."""

from prometheus_client import REGISTRY, Counter
from litellm.integrations.custom_logger import CustomLogger

_LABELS = ["model_group"]


def _counter(name, doc, labels):
    # Reuse the registered counter if LiteLLM loads this module twice.
    try:
        return Counter(name, doc, labels)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


AUDIO = _counter("transcription_audio_seconds", "Seconds of audio transcribed", _LABELS)
PROCESSING = _counter("transcription_processing_seconds", "Wall-clock seconds spent transcribing", _LABELS)
WORDS = _counter("transcription_words", "Words in transcription output", _LABELS)
REQUESTS = _counter("transcription_requests", "Successful transcriptions, by whether audio length was known", _LABELS + ["duration_known"])

# Start the whisper series at 0 so increase() counts the first transcription after a restart.
for _c in (AUDIO, PROCESSING, WORDS):
    _c.labels("whisper")
for _known in ("true", "false"):
    REQUESTS.labels("whisper", _known)


class TranscriptionMetrics(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            slo = kwargs.get("standard_logging_object") or {}
            if slo.get("call_type") not in ("atranscription", "transcription"):
                return
            group = slo.get("model_group") or kwargs.get("model") or "unknown"
            hidden = getattr(response_obj, "_hidden_params", None) or {}
            audio = hidden.get("audio_transcription_duration") or getattr(response_obj, "duration", None)
            REQUESTS.labels(group, "true" if audio else "false").inc()
            if not audio:
                return
            AUDIO.labels(group).inc(float(audio))
            PROCESSING.labels(group).inc(max((end_time - start_time).total_seconds(), 0.0))
            WORDS.labels(group).inc(len((getattr(response_obj, "text", "") or "").split()))
        except Exception:
            pass


proxy_handler_instance = TranscriptionMetrics()
