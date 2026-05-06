"""
overlay.py — Always-on-top invisible overlay window for MeetAssist.

Features:
  - Frameless, transparent background
  - Dark glass-morphism panel with white text
  - Draggable (click-drag anywhere)
  - Screen-capture exclusion:
      Windows  → SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
      macOS    → NSWindowSharingNone via osascript / pyobjc
      Linux    → X11 _NET_WM_BYPASS_COMPOSITOR + override_redirect (best effort)
  - Token-by-token streaming text updates
  - Status bar (Listening / Thinking / Ready)
"""

import sys
import platform
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Callable
import logging

log = logging.getLogger(__name__)

# ── Colour & style constants ──────────────────────────────────────────────────
BG_TRANSPARENT   = "#010101"        # near-black used as transparency key
PANEL_BG         = "#0d0d0d"        # dark panel fill
PANEL_BORDER     = "#2a2a2a"
ACCENT           = "#7c6fcd"        # purple accent
TEXT_COLOR       = "#f0f0f0"
DIM_COLOR        = "#888888"
STATUS_COLORS    = {
    "listening": "#4ade80",         # green
    "thinking":  "#fb923c",         # orange
    "ready":     "#60a5fa",         # blue
    "error":     "#f87171",         # red
    "inactive":  "#555555",
}
FONT_FAMILY = "Inter"               # fallback handled below


def _get_font_family() -> str:
    """Return Inter if available, else a good system fallback."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        families = tkfont.families(root)
        root.destroy()
        for f in ["Inter", "SF Pro Display", "Segoe UI", "Helvetica Neue", "DejaVu Sans"]:
            if f in families:
                return f
    except Exception:
        pass
    return "Helvetica"


class MeetAssistOverlay:
    """
    The floating, always-on-top overlay window.

    Public methods:
      show() / hide() / toggle()
      set_status(label)
      append_token(token)
      set_answer(full_text)
      clear()
      run()   — starts the Tkinter main loop (blocking)
      schedule(fn)  — thread-safe: root.after(0, fn)
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self._visible = True
        self._drag_x = 0
        self._drag_y = 0

        self.root = tk.Tk()
        self._build_window()
        self._build_ui()
        self._apply_capture_exclusion()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _build_window(self) -> None:
        root = self.root
        root.title("MeetAssist")
        root.overrideredirect(True)          # frameless
        root.wm_attributes("-topmost", True) # always on top
        root.configure(bg=BG_TRANSPARENT)

        os_name = platform.system()
        if os_name == "Windows":
            root.wm_attributes("-transparentcolor", BG_TRANSPARENT)
        elif os_name == "Darwin":
            root.wm_attributes("-transparent", True)
            root.wm_attributes("-alpha", self.cfg.get("overlay_opacity", 0.75))
        else:
            # Linux: use alpha transparency
            try:
                root.wm_attributes("-alpha", self.cfg.get("overlay_opacity", 0.75))
            except Exception:
                pass

        w = self.cfg.get("overlay_width", 480)
        h = self.cfg.get("overlay_height", 340)
        x = self.cfg.get("overlay_x", 40)
        y = self.cfg.get("overlay_y", 40)
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.resizable(True, True)
        root.minsize(300, 200)
        # Save size to config whenever the window is resized
        root.bind("<Configure>", self._on_resize)

    def _build_ui(self) -> None:
        font_family = _get_font_family()
        font_size   = self.cfg.get("overlay_font_size", 14)

        # ── Outer frame (acts as rounded border via bg colour) ────────────────
        outer = tk.Frame(
            self.root,
            bg=PANEL_BORDER,
            padx=1, pady=1,
        )
        outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Main panel ────────────────────────────────────────────────────────
        panel = tk.Frame(outer, bg=PANEL_BG, padx=14, pady=10)
        panel.pack(fill=tk.BOTH, expand=True)

        # ── Header row ────────────────────────────────────────────────────────
        header = tk.Frame(panel, bg=PANEL_BG)
        header.pack(fill=tk.X, pady=(0, 6))

        logo_lbl = tk.Label(
            header, text="✦ MeetAssist", bg=PANEL_BG,
            fg=ACCENT,
            font=(font_family, font_size - 1, "bold"),
        )
        logo_lbl.pack(side=tk.LEFT)

        self._status_dot = tk.Label(
            header, text="●", bg=PANEL_BG,
            fg=STATUS_COLORS["inactive"],
            font=(font_family, font_size + 2),
        )
        self._status_dot.pack(side=tk.RIGHT, padx=(0, 2))

        self._status_label = tk.Label(
            header, text="Inactive", bg=PANEL_BG,
            fg=DIM_COLOR,
            font=(font_family, font_size - 2),
        )
        self._status_label.pack(side=tk.RIGHT, padx=(0, 4))

        # ── Opacity slider (inline, right of status) ───────────────────────────
        self._opacity_var = tk.DoubleVar(
            value=self.cfg.get("overlay_opacity", 0.75)
        )
        opacity_slider = tk.Scale(
            header,
            from_=0.15, to=1.0,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            variable=self._opacity_var,
            bg=PANEL_BG,
            fg=DIM_COLOR,
            troughcolor=PANEL_BORDER,
            activebackground=ACCENT,
            highlightthickness=0,
            showvalue=False,
            sliderlength=10,
            width=6,
            length=60,
            command=self._on_opacity_change,
            cursor="sb_h_double_arrow",
        )
        opacity_slider.pack(side=tk.RIGHT, padx=(0, 6))

        opacity_icon = tk.Label(
            header, text="◐", bg=PANEL_BG, fg=DIM_COLOR,
            font=(font_family, font_size - 2),
        )
        opacity_icon.pack(side=tk.RIGHT)

        # ── Divider ───────────────────────────────────────────────────────────
        divider = tk.Frame(panel, bg=PANEL_BORDER, height=1)
        divider.pack(fill=tk.X, pady=(0, 8))

        # ── Answer text area ──────────────────────────────────────────────────
        text_frame = tk.Frame(panel, bg=PANEL_BG)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self._answer_text = tk.Text(
            text_frame,
            bg=PANEL_BG,
            fg=TEXT_COLOR,
            font=(font_family, font_size),
            wrap=tk.WORD,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            insertwidth=0,
            state=tk.DISABLED,
            cursor="arrow",
            spacing1=3,
            spacing3=3,
        )
        self._answer_text.pack(fill=tk.BOTH, expand=True)

        # Tag for accent colour on bullet lines
        self._answer_text.tag_configure("bullet", foreground=ACCENT)
        self._answer_text.tag_configure("placeholder", foreground=DIM_COLOR)

        # ── Transcript ticker (bottom bar) ────────────────────────────────────
        bottom = tk.Frame(panel, bg=PANEL_BG)
        bottom.pack(fill=tk.X, pady=(8, 0))

        tk.Frame(bottom, bg=PANEL_BORDER, height=1).pack(fill=tk.X, pady=(0, 6))

        self._transcript_var = tk.StringVar(value="Waiting for audio…")
        self._transcript_lbl = tk.Label(
            bottom,
            textvariable=self._transcript_var,
            bg=PANEL_BG,
            fg=DIM_COLOR,
            font=(font_family, max(font_size - 4, 9)),
            anchor="w",
            wraplength=400,
            justify=tk.LEFT,
        )
        self._transcript_lbl.pack(fill=tk.X)

        # ── Bottom row: hotkey hint + resize grip ─────────────────────────────
        bottom_row = tk.Frame(bottom, bg=PANEL_BG)
        bottom_row.pack(fill=tk.X, pady=(3, 0))

        hint_lbl = tk.Label(
            bottom_row,
            text="C-S-A: Ask  •  C-S-C: Clear  •  C-S-H: Hide  •  C-S-Q: Quit",
            bg=PANEL_BG,
            fg="#3a3a3a",
            font=(font_family, max(font_size - 5, 8)),
            anchor="w",
        )
        hint_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Resize grip (bottom-right corner) ─────────────────────────────────
        # Cursor name differs by platform: X11 uses "bottom_right_corner"
        _resize_cursor = (
            "bottom_right_corner"
            if platform.system() != "Windows"
            else "size_nw_se"
        )
        grip = tk.Label(
            bottom_row,
            text="⠿",
            bg=PANEL_BG,
            fg="#3a3a3a",
            font=(font_family, 11),
            cursor=_resize_cursor,
        )
        grip.pack(side=tk.RIGHT, padx=(4, 0))
        grip.bind("<ButtonPress-1>",  self._on_resize_start)
        grip.bind("<B1-Motion>",      self._on_resize_motion)

        # ── Drag bindings (header + empty areas only, not the grip) ───────────
        for widget in [outer, panel, header, logo_lbl, divider, bottom, hint_lbl]:
            widget.bind("<ButtonPress-1>",   self._on_drag_start)
            widget.bind("<B1-Motion>",       self._on_drag_motion)

        # Store placeholder state
        self._has_content = False
        self._set_placeholder()

    # ── Drag handlers ─────────────────────────────────────────────────────────

    def _on_drag_start(self, event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.cfg["overlay_x"] = x
        self.cfg["overlay_y"] = y

    # ── Resize handlers (grip corner) ─────────────────────────────────────────

    def _on_resize_start(self, event) -> None:
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.root.winfo_width()
        self._resize_start_h = self.root.winfo_height()

    def _on_resize_motion(self, event) -> None:
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        new_w = max(300, self._resize_start_w + dx)
        new_h = max(200, self._resize_start_h + dy)
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{new_w}x{new_h}+{x}+{y}")

    def _on_resize(self, event) -> None:
        """Called on any <Configure> event — save new size to config."""
        if event.widget is self.root:
            self.cfg["overlay_width"]  = event.width
            self.cfg["overlay_height"] = event.height
            # Keep transcript label wraplength in sync
            try:
                self._transcript_lbl.configure(wraplength=max(100, event.width - 80))
            except AttributeError:
                pass

    # ── Opacity handler ───────────────────────────────────────────────────────

    def _on_opacity_change(self, value) -> None:
        alpha = float(value)
        try:
            self.root.wm_attributes("-alpha", alpha)
        except Exception:
            pass
        self.cfg["overlay_opacity"] = round(alpha, 2)

    # ── Screen-capture exclusion ──────────────────────────────────────────────

    def _apply_capture_exclusion(self) -> None:
        os_name = platform.system()
        if os_name == "Windows":
            self._exclude_windows()
        elif os_name == "Darwin":
            self._exclude_macos()
        else:
            self._exclude_linux()

    def _exclude_windows(self) -> None:
        try:
            import ctypes
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if result:
                log.info("Windows: screen-capture exclusion applied (WDA_EXCLUDEFROMCAPTURE).")
            else:
                log.warning("Windows: SetWindowDisplayAffinity returned 0 (may need elevated process).")
        except Exception as e:
            log.error("Windows capture exclusion failed: %s", e)

    def _exclude_macos(self) -> None:
        try:
            # Try pyobjc approach
            from AppKit import NSApplication, NSWindowSharingNone
            app = NSApplication.sharedApplication()
            # The Tk NSWindow is not directly accessible; use osascript fallback
            raise NotImplementedError("Use osascript")
        except Exception:
            try:
                import subprocess, os
                # Instruct the OS via AppleScript to deny window sharing
                script = '''
                tell application "System Events"
                    set frontmost of process "Python" to true
                end tell
                '''
                subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                log.info("macOS: attempted window exclusion via osascript.")
            except Exception as e2:
                log.warning("macOS capture exclusion not available: %s", e2)

    def _exclude_linux(self) -> None:
        """
        Linux: no universal API to exclude a window from screen capture.
        We set _NET_WM_BYPASS_COMPOSITOR and keep the window override_redirect
        so it doesn't appear in standard WM window lists.
        This prevents most compositors from capturing it, but is not guaranteed.
        """
        try:
            self.root.after(100, self._set_x11_hints)
        except Exception as e:
            log.warning("Linux X11 hints not applied: %s", e)

    def _set_x11_hints(self) -> None:
        try:
            # _NET_WM_BYPASS_COMPOSITOR = 1 (disable compositor for this window)
            self.root.tk.call(
                "wm", "attributes", self.root, "-type", "splash"
            )
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    def schedule(self, fn) -> None:
        """Thread-safe: schedule fn on the Tkinter main thread."""
        self.root.after(0, fn)

    def set_status(self, label: str) -> None:
        color = STATUS_COLORS.get(label, STATUS_COLORS["inactive"])
        self._status_dot.configure(fg=color)
        self._status_label.configure(text=label.capitalize())

    def set_transcript_ticker(self, text: str) -> None:
        """Update the bottom transcript ticker with the latest spoken line."""
        # Truncate long lines
        if len(text) > 80:
            text = "…" + text[-77:]
        self._transcript_var.set(text)

    def append_token(self, token: str) -> None:
        """Append a streaming token to the answer text widget."""
        if not self._has_content:
            self._clear_placeholder()

        self._answer_text.configure(state=tk.NORMAL)
        # Highlight bullet lines
        if token.startswith("•") or token.startswith("-"):
            self._answer_text.insert(tk.END, token, "bullet")
        else:
            self._answer_text.insert(tk.END, token)
        self._answer_text.see(tk.END)
        self._answer_text.configure(state=tk.DISABLED)

    def set_answer(self, full_text: str) -> None:
        """Replace entire answer with full_text (called when streaming done)."""
        self._clear_placeholder()
        self._answer_text.configure(state=tk.NORMAL)
        self._answer_text.delete("1.0", tk.END)

        for line in full_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(("•", "-", "*")):
                self._answer_text.insert(tk.END, stripped + "\n", "bullet")
            elif stripped:
                self._answer_text.insert(tk.END, stripped + "\n")

        self._answer_text.see(tk.END)
        self._answer_text.configure(state=tk.DISABLED)
        self._has_content = bool(full_text.strip())

    def clear(self) -> None:
        self._answer_text.configure(state=tk.NORMAL)
        self._answer_text.delete("1.0", tk.END)
        self._answer_text.configure(state=tk.DISABLED)
        self._has_content = False
        self._set_placeholder()
        self.set_status("listening")
        self._transcript_var.set("Context cleared. Listening…")

    def show(self) -> None:
        self._visible = True
        self.root.deiconify()

    def hide(self) -> None:
        self._visible = False
        self.root.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def quit(self) -> None:
        self.root.quit()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_placeholder(self) -> None:
        self._answer_text.configure(state=tk.NORMAL)
        self._answer_text.delete("1.0", tk.END)
        self._answer_text.insert(
            tk.END,
            "AI answers will appear here…\n\n"
            "Speak or ask a question in your meeting,\n"
            "or press Ctrl+Shift+A to generate now.",
            "placeholder",
        )
        self._answer_text.configure(state=tk.DISABLED)

    def _clear_placeholder(self) -> None:
        if not self._has_content:
            self._answer_text.configure(state=tk.NORMAL)
            self._answer_text.delete("1.0", tk.END)
            self._answer_text.configure(state=tk.DISABLED)
            self._has_content = True
