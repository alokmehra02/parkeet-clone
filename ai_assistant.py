"""
ai_assistant.py — GPT-4o streaming assistant for MeetAssist.

Sends the rolling transcript context to OpenAI and streams the response
token-by-token into the overlay via a callback.
"""

import threading
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a silent real-time meeting assistant. "
    "The user is in a Google Meet call. "
    "Based on the conversation transcript provided, give a concise answer "
    "or talking point the user can use. "
    "Be brief — maximum 3 bullet points. "
    "Use plain Unicode bullet points (•). "
    "Do not explain that you are an AI. "
    "Do not add any preamble or closing remarks."
)


class AIAssistant:
    """
    Streams GPT-4o completions into an overlay window.

    on_token(str)   — called with each streamed token (schedule on main thread)
    on_done(str)    — called with the full answer text when streaming completes
    on_error(str)   — called when an error occurs
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        on_token: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        schedule_fn: Optional[Callable] = None,   # root.after(0, fn)
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.on_token = on_token
        self.on_done = on_done
        self.on_error = on_error
        self.schedule_fn = schedule_fn
        self._busy = False

    def _schedule(self, fn) -> None:
        if self.schedule_fn:
            self.schedule_fn(fn)
        else:
            fn()

    def is_busy(self) -> bool:
        return self._busy

    def generate(self, transcript_context: str) -> None:
        """
        Non-blocking: spawns a daemon thread to stream the GPT-4o response.
        Silently skips if a generation is already in progress.
        """
        if self._busy:
            log.info("AI generation already in progress; skipping.")
            return
        if not transcript_context.strip():
            log.info("Empty transcript context; nothing to generate.")
            return

        self._busy = True
        thread = threading.Thread(
            target=self._stream_response,
            args=(transcript_context,),
            daemon=True,
        )
        thread.start()

    def _stream_response(self, transcript: str) -> None:
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)

            user_content = (
                "Here is the recent meeting transcript:\n\n"
                f"{transcript}\n\n"
                "Please provide your response now."
            )

            full_text = ""
            with client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                stream=True,
                max_tokens=300,
                temperature=0.4,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        token = delta.content
                        full_text += token
                        if self.on_token:
                            captured = token
                            self._schedule(lambda t=captured: self.on_token(t))

            if self.on_done:
                captured_full = full_text
                self._schedule(lambda t=captured_full: self.on_done(t))

        except Exception as e:
            log.error("AI generation error: %s", e)
            err_msg = str(e)
            if self.on_error:
                self._schedule(lambda m=err_msg: self.on_error(m))
        finally:
            self._busy = False
