"""
audio_capture.py — Capture system audio (loopback) and microphone input.

Streams 3-second chunks of PCM audio into a queue for transcription.
Supports:
  - Linux:   pulse/pipewire monitor source (loopback)
  - Windows: WASAPI loopback / Stereo Mix
  - macOS:   BlackHole or Loopback virtual device
"""

import queue
import threading
import numpy as np
import sounddevice as sd
from typing import Callable, Optional
import logging

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000   # Whisper expects 16 kHz
CHUNK_SECONDS = 3
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS
CHANNELS = 1


def _find_loopback_device() -> Optional[int]:
    """
    Scan sounddevice device list for a loopback / monitor source.
    Returns device index or None if not found (caller can use default).
    """
    keywords = [
        "loopback", "stereo mix", "monitor",
        "what u hear", "wave out mix", "blackhole",
        "pulse", "pipewire",
    ]
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        name_lower = dev["name"].lower()
        if dev["max_input_channels"] > 0:
            if any(kw in name_lower for kw in keywords):
                log.info("Auto-detected loopback device: [%d] %s", idx, dev["name"])
                return idx
    return None


def _find_mic_device() -> Optional[int]:
    """Return default input device index, or None."""
    try:
        info = sd.query_devices(kind="input")
        return info["index"] if isinstance(info, dict) else None
    except Exception:
        return None


class AudioCapture:
    """
    Captures audio from a loopback (system output) device and optionally
    mixes in microphone input.  Enqueues raw float32 numpy arrays.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        mix_mic: bool = False,
        loopback_device: Optional[int] = None,
        mic_device: Optional[int] = None,
    ) -> None:
        self.audio_queue = audio_queue
        self.mix_mic = mix_mic
        self._loopback_device = loopback_device
        self._mic_device = mic_device
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer = np.zeros(0, dtype=np.float32)
        self._mic_buffer = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()

    # ── Internal callbacks ────────────────────────────────────────────────

    def _loopback_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Loopback audio status: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        with self._lock:
            self._buffer = np.concatenate([self._buffer, mono])
            self._flush_if_ready()

    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Mic audio status: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        with self._lock:
            self._mic_buffer = np.concatenate([self._mic_buffer, mono])

    def _flush_if_ready(self) -> None:
        """Called under lock — if we have a full chunk, push to queue."""
        while len(self._buffer) >= CHUNK_SAMPLES:
            chunk = self._buffer[:CHUNK_SAMPLES].copy()
            self._buffer = self._buffer[CHUNK_SAMPLES:]

            # Mix in mic if available and same length
            if self.mix_mic and len(self._mic_buffer) >= CHUNK_SAMPLES:
                mic_chunk = self._mic_buffer[:CHUNK_SAMPLES].copy()
                self._mic_buffer = self._mic_buffer[CHUNK_SAMPLES:]
                chunk = np.clip(chunk * 0.7 + mic_chunk * 0.3, -1.0, 1.0)

            self.audio_queue.put(chunk)

    # ── Public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        # Resolve devices
        lb_device = self._loopback_device
        if lb_device is None:
            lb_device = _find_loopback_device()

        mic_device = self._mic_device
        if mic_device is None and self.mix_mic:
            mic_device = _find_mic_device()

        streams = []
        try:
            # Loopback stream
            lb_stream = sd.InputStream(
                device=lb_device,
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                dtype="float32",
                callback=self._loopback_callback,
                blocksize=1024,
            )
            lb_stream.start()
            streams.append(lb_stream)
            log.info(
                "Loopback stream started on device: %s",
                lb_device if lb_device is not None else "default",
            )

            # Optional mic stream
            if self.mix_mic and mic_device is not None:
                mic_stream = sd.InputStream(
                    device=mic_device,
                    channels=CHANNELS,
                    samplerate=SAMPLE_RATE,
                    dtype="float32",
                    callback=self._mic_callback,
                    blocksize=1024,
                )
                mic_stream.start()
                streams.append(mic_stream)
                log.info("Mic stream started on device: %s", mic_device)

            # Keep thread alive until stopped
            while self._running:
                threading.Event().wait(0.5)

        except Exception as e:
            log.error("Audio capture error: %s", e)
            # Signal the queue so the consumer doesn't block forever
            self.audio_queue.put(None)
        finally:
            for s in streams:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
            log.info("Audio capture stopped.")


def list_audio_devices() -> list[dict]:
    """Return a list of dicts describing all sounddevice devices."""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        result.append({
            "index": idx,
            "name": dev["name"],
            "max_input_channels": dev["max_input_channels"],
            "max_output_channels": dev["max_output_channels"],
            "default_samplerate": dev["default_samplerate"],
        })
    return result
