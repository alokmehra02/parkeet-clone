"""
transcription.py — Whisper-based transcription for audio chunks.

Supports:
  - "whisper-api"     → OpenAI cloud API (whisper-1)
  - "faster-whisper"  → Local faster-whisper library (offline, GPU optional)

Runs in a daemon thread; feeds transcript strings into a result queue.
Keeps a rolling 30-second context buffer of transcript text.
"""

import io
import queue
import threading
import numpy as np
import logging
import time
from collections import deque
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Rolling context window: store last N transcript chunks
MAX_CONTEXT_CHUNKS = 10   # ≈ 30 seconds at 3 s/chunk


class TranscriptBuffer:
    """Thread-safe rolling buffer of the last N transcript lines."""

    def __init__(self, maxlen: int = MAX_CONTEXT_CHUNKS) -> None:
        self._lock = threading.Lock()
        self._lines: deque[str] = deque(maxlen=maxlen)

    def add(self, text: str) -> None:
        with self._lock:
            stripped = text.strip()
            if stripped:
                self._lines.append(stripped)

    def get_context(self) -> str:
        with self._lock:
            return "\n".join(self._lines)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def has_question(self) -> bool:
        """Return True if the most recent line looks like a question."""
        with self._lock:
            if not self._lines:
                return False
            return self._lines[-1].rstrip().endswith("?")


class WhisperAPITranscriber:
    """Transcribes audio chunks via the OpenAI Whisper API."""

    def __init__(self, api_key: str) -> None:
        import openai
        self._client = openai.OpenAI(api_key=api_key)

    def transcribe(self, audio_chunk: np.ndarray, sample_rate: int = 16_000) -> str:
        """Convert float32 numpy array → PCM wav bytes → API call → text."""
        import openai
        wav_bytes = _numpy_to_wav(audio_chunk, sample_rate)
        if len(wav_bytes) < 500:
            return ""
        try:
            response = self._client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", wav_bytes, "audio/wav"),
                language="en",
            )
            return response.text.strip()
        except openai.APIError as e:
            log.error("Whisper API error: %s", e)
            return ""


class FasterWhisperTranscriber:
    """Transcribes audio chunks using the local faster-whisper library."""

    def __init__(self, model_size: str = "base") -> None:
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            log.info("faster-whisper model '%s' loaded.", model_size)
        except ImportError:
            log.error("faster-whisper not installed. Run: pip install faster-whisper")
            raise

    def transcribe(self, audio_chunk: np.ndarray, sample_rate: int = 16_000) -> str:
        segments, _ = self._model.transcribe(audio_chunk, language="en", beam_size=5)
        return " ".join(s.text for s in segments).strip()


# ── Transcription Engine ──────────────────────────────────────────────────────

class TranscriptionEngine:
    """
    Pulls audio chunks from audio_queue, transcribes them, appends to the
    TranscriptBuffer, and invokes on_transcript callback on the main thread
    via the provided schedule function.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        buffer: TranscriptBuffer,
        on_transcript: Callable[[str], None],
        schedule_fn: Callable,        # root.after(0, fn) equivalent
        engine: str = "whisper-api",
        api_key: str = "",
    ) -> None:
        self.audio_queue = audio_queue
        self.buffer = buffer
        self.on_transcript = on_transcript
        self.schedule_fn = schedule_fn
        self.engine = engine
        self.api_key = api_key
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._transcriber = None

    def _build_transcriber(self):
        if self.engine == "faster-whisper":
            return FasterWhisperTranscriber()
        else:
            return WhisperAPITranscriber(self.api_key)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        # Unblock queue.get
        self.audio_queue.put(None)

    def _run(self) -> None:
        try:
            self._transcriber = self._build_transcriber()
        except Exception as e:
            log.error("Failed to build transcriber: %s", e)
            return

        log.info("Transcription engine started (%s).", self.engine)
        while self._running:
            try:
                chunk = self.audio_queue.get(timeout=5)
                if chunk is None:
                    continue

                # Skip near-silent chunks to avoid wasting API calls
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                if rms < 0.002:
                    continue

                text = self._transcriber.transcribe(chunk)
                if text:
                    self.buffer.add(text)
                    captured = text   # capture for lambda
                    self.schedule_fn(lambda t=captured: self.on_transcript(t))
            except queue.Empty:
                continue
            except Exception as e:
                log.error("Transcription error: %s", e)
                time.sleep(1)
        log.info("Transcription engine stopped.")


# ── Utility ───────────────────────────────────────────────────────────────────

def _numpy_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32 numpy array to an in-memory WAV file (bytes)."""
    import struct
    import wave

    # Convert float32 [-1, 1] → int16
    pcm = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
