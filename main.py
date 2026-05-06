"""
main.py — Entry point for MeetAssist, the invisible AI meeting assistant.

Orchestrates:
  1. Config load / first-run setup dialog
  2. SQLite session creation
  3. Audio capture (loopback + optional mic)
  4. Transcription engine (Whisper API or faster-whisper)
  5. GPT-4o streaming AI assistant
  6. Always-on-top overlay window
  7. Global hotkeys
  8. Clean shutdown
"""

import logging
import queue
import sys
import threading
import signal
import atexit

# ── Logging setup (before any imports from our modules) ─────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("meetassist")

# ── Our modules ───────────────────────────────────────────────────────────────
from config import load_config, save_config, is_first_run
from database import create_session, end_session, save_transcript, save_answer
from audio_capture import AudioCapture
from transcription import TranscriptionEngine, TranscriptBuffer
from ai_assistant import AIAssistant
from overlay import MeetAssistOverlay
from hotkeys import HotkeyManager
from setup_dialog import SetupDialog


class MeetAssistApp:
    """
    Top-level application controller.
    Wires all subsystems together and owns the main thread (Tkinter).
    """

    def __init__(self) -> None:
        # ── Config ────────────────────────────────────────────────────────────
        self.cfg = load_config()
        if is_first_run(self.cfg):
            updated = SetupDialog(self.cfg).run()
            if not updated:
                log.info("Setup cancelled by user. Exiting.")
                sys.exit(0)
            self.cfg = updated
            save_config(self.cfg)

        # ── DB session ────────────────────────────────────────────────────────
        self.session_id = create_session()
        log.info("New session created: id=%d", self.session_id)

        # ── Shared state ──────────────────────────────────────────────────────
        self.audio_queue: queue.Queue = queue.Queue(maxsize=20)
        self.transcript_buffer = TranscriptBuffer(maxlen=10)
        self._generating = False
        self._shutdown_event = threading.Event()

        # ── Overlay (must be created first — owns Tkinter main loop) ─────────
        self.overlay = MeetAssistOverlay(self.cfg)

        # ── AI assistant ──────────────────────────────────────────────────────
        self.assistant = AIAssistant(
            api_key=self.cfg["openai_api_key"],
            model=self.cfg.get("model", "gpt-4o"),
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            schedule_fn=self.overlay.schedule,
        )

        # ── Audio capture ─────────────────────────────────────────────────────
        self.audio_capture = AudioCapture(
            audio_queue=self.audio_queue,
            mix_mic=False,  # loopback only by default
        )

        # ── Transcription engine ──────────────────────────────────────────────
        self.transcription = TranscriptionEngine(
            audio_queue=self.audio_queue,
            buffer=self.transcript_buffer,
            on_transcript=self._on_transcript,
            schedule_fn=self.overlay.schedule,
            engine=self.cfg.get("transcription_engine", "whisper-api"),
            api_key=self.cfg["openai_api_key"],
        )

        # ── Hotkeys ───────────────────────────────────────────────────────────
        self.hotkeys = HotkeyManager(schedule_fn=self.overlay.schedule)
        self._register_hotkeys()

        # ── Atexit / signal ───────────────────────────────────────────────────
        atexit.register(self._shutdown)
        signal.signal(signal.SIGINT, lambda *_: self._request_quit())
        signal.signal(signal.SIGTERM, lambda *_: self._request_quit())

    # ── Hotkey registration ───────────────────────────────────────────────────

    def _register_hotkeys(self) -> None:
        hk = self.cfg
        self.hotkeys.register(hk.get("hotkey_toggle", "ctrl+shift+h"), self._on_hotkey_toggle)
        self.hotkeys.register(hk.get("hotkey_ask",    "ctrl+shift+a"), self._on_hotkey_ask)
        self.hotkeys.register(hk.get("hotkey_clear",  "ctrl+shift+c"), self._on_hotkey_clear)
        self.hotkeys.register(hk.get("hotkey_quit",   "ctrl+shift+q"), self._on_hotkey_quit)

    # ── Callbacks (all called on main thread via overlay.schedule) ────────────

    def _on_transcript(self, text: str) -> None:
        """Received a new transcription chunk."""
        log.info("Transcript: %s", text)
        self.overlay.set_transcript_ticker(text)
        self.overlay.set_status("listening")

        # Persist to DB in background thread
        sid = self.session_id
        threading.Thread(
            target=save_transcript, args=(sid, text), daemon=True
        ).start()

        # Auto-trigger AI if a question was detected
        if self.transcript_buffer.has_question() and not self.assistant.is_busy():
            log.info("Question detected — triggering AI generation.")
            self._trigger_ai()

    def _on_token(self, token: str) -> None:
        """Streaming token received from GPT-4o."""
        self.overlay.append_token(token)

    def _on_done(self, full_text: str) -> None:
        """Streaming complete — persist answer."""
        self.overlay.set_status("ready")
        context = self.transcript_buffer.get_context()
        sid = self.session_id
        threading.Thread(
            target=save_answer, args=(sid, context, full_text), daemon=True
        ).start()
        log.info("AI answer saved (%d chars).", len(full_text))

    def _on_error(self, msg: str) -> None:
        self.overlay.set_status("error")
        self.overlay.set_answer(f"⚠ Error: {msg}")
        log.error("AI error: %s", msg)

    # ── Hotkey handlers ───────────────────────────────────────────────────────

    def _on_hotkey_toggle(self) -> None:
        self.overlay.toggle()

    def _on_hotkey_ask(self) -> None:
        log.info("Manual AI trigger via hotkey.")
        self._trigger_ai()

    def _on_hotkey_clear(self) -> None:
        log.info("Context cleared via hotkey.")
        self.transcript_buffer.clear()
        self.overlay.clear()

    def _on_hotkey_quit(self) -> None:
        log.info("Quit hotkey pressed.")
        self._request_quit()

    # ── AI trigger ────────────────────────────────────────────────────────────

    def _trigger_ai(self) -> None:
        context = self.transcript_buffer.get_context()
        if not context.strip():
            self.overlay.set_transcript_ticker("No transcript yet — speak first.")
            return
        self.overlay.set_status("thinking")
        self.overlay.clear()
        self.assistant.generate(context)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _request_quit(self) -> None:
        """Graceful shutdown request — safe to call from any thread."""
        self.overlay.schedule(self._shutdown_and_quit)

    def _shutdown_and_quit(self) -> None:
        self._shutdown()
        self.overlay.quit()

    def _shutdown(self) -> None:
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        log.info("Shutting down MeetAssist…")
        self.hotkeys.stop()
        self.audio_capture.stop()
        self.transcription.stop()
        save_config(self.cfg)
        end_session(self.session_id)
        log.info("Session ended. Goodbye.")

    def run(self) -> None:
        """Start all subsystems and enter the Tkinter main loop."""
        self.overlay.set_status("listening")

        # Start background workers
        self.audio_capture.start()
        self.transcription.start()
        self.hotkeys.start()

        log.info(
            "MeetAssist running. "
            "Hotkeys: %s=toggle  %s=ask  %s=clear  %s=quit",
            self.cfg.get("hotkey_toggle", "ctrl+shift+h"),
            self.cfg.get("hotkey_ask",    "ctrl+shift+a"),
            self.cfg.get("hotkey_clear",  "ctrl+shift+c"),
            self.cfg.get("hotkey_quit",   "ctrl+shift+q"),
        )

        # Blocking — runs Tkinter main loop on this thread
        self.overlay.run()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    try:
        app = MeetAssistApp()
        app.run()
    except KeyboardInterrupt:
        log.info("Interrupted. Exiting.")
    except Exception as e:
        log.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
