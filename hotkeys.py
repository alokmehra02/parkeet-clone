"""
hotkeys.py — Global hotkey registration for MeetAssist.

Uses the `keyboard` library for cross-platform global hotkeys.
All callbacks are invoked in the keyboard library's thread, so use
schedule_fn (root.after) to dispatch back to the Tkinter main thread.
"""

import logging
import threading
from typing import Callable, Dict, Optional

log = logging.getLogger(__name__)


class HotkeyManager:
    """
    Registers and manages global hotkeys.

    Usage:
        hm = HotkeyManager(schedule_fn=root.after)
        hm.register("ctrl+shift+h", on_toggle)
        hm.start()
        ...
        hm.stop()
    """

    def __init__(self, schedule_fn: Optional[Callable] = None) -> None:
        self._schedule_fn = schedule_fn
        self._bindings: Dict[str, Callable] = {}
        self._started = False
        self._hooked_ids = []

    def register(self, hotkey: str, callback: Callable) -> None:
        """Register a global hotkey string and associated callback."""
        self._bindings[hotkey.lower()] = callback

    def _make_safe_callback(self, cb: Callable) -> Callable:
        """Wrap cb so it runs on the main thread via schedule_fn."""
        if self._schedule_fn:
            def safe():
                self._schedule_fn(cb)
            return safe
        return cb

    def start(self) -> None:
        """Start listening for hotkeys (must be called after Tkinter window exists)."""
        if self._started:
            return
        try:
            import keyboard as kb
            for hotkey, cb in self._bindings.items():
                safe_cb = self._make_safe_callback(cb)
                hid = kb.add_hotkey(hotkey, safe_cb)
                self._hooked_ids.append((hotkey, hid))
                log.info("Hotkey registered: %s", hotkey)
            self._started = True
            log.info("HotkeyManager started with %d hotkeys.", len(self._bindings))
        except ImportError:
            log.error(
                "The `keyboard` package is not installed. "
                "Hotkeys disabled. Run: pip install keyboard"
            )
        except Exception as e:
            log.error("HotkeyManager start error: %s", e)

    def stop(self) -> None:
        """Unregister all hotkeys."""
        try:
            import keyboard as kb
            for hotkey, _ in self._hooked_ids:
                try:
                    kb.remove_hotkey(hotkey)
                except Exception:
                    pass
        except ImportError:
            pass
        self._hooked_ids.clear()
        self._started = False
        log.info("HotkeyManager stopped.")
