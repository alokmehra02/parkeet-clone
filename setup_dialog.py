"""
setup_dialog.py — First-run setup dialog for MeetAssist.

Prompts the user for their OpenAI API key and saves it to config.
Also allows choosing transcription engine and opacity.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import platform

# Colour palette (matches overlay.py)
BG       = "#0d0d0d"
PANEL    = "#161616"
ACCENT   = "#7c6fcd"
TEXT     = "#f0f0f0"
DIM      = "#888888"
ENTRY_BG = "#1e1e1e"
BTN_BG   = "#7c6fcd"
BTN_FG   = "#ffffff"
BORDER   = "#2a2a2a"


class SetupDialog:
    """
    Modal dialog shown on first run.
    Returns updated config dict on OK, or raises SystemExit on cancel.
    """

    def __init__(self, cfg: dict) -> None:
        self.cfg = dict(cfg)
        self.result: dict | None = None

        self.root = tk.Tk()
        self.root.title("MeetAssist — First Time Setup")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # Center on screen
        w, h = 520, 460
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # Make topmost during setup
        self.root.wm_attributes("-topmost", True)
        if platform.system() != "Windows":
            try:
                self.root.wm_attributes("-alpha", 0.97)
            except Exception:
                pass

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 28, "pady": 0}

        # ── Title ──────────────────────────────────────────────────────────────
        tk.Label(
            self.root, text="✦ MeetAssist Setup",
            bg=BG, fg=ACCENT,
            font=("Helvetica", 20, "bold"),
        ).pack(pady=(30, 4))

        tk.Label(
            self.root,
            text="Configure your AI meeting assistant",
            bg=BG, fg=DIM,
            font=("Helvetica", 11),
        ).pack(pady=(0, 20))

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X, **pad, pady=(0, 20))

        # ── API Key ───────────────────────────────────────────────────────────
        self._section_label("OpenAI API Key")

        self._api_key_var = tk.StringVar(value=self.cfg.get("openai_api_key", ""))
        key_frame = tk.Frame(self.root, bg=BG)
        key_frame.pack(fill=tk.X, **pad, pady=(0, 16))

        self._key_entry = tk.Entry(
            key_frame,
            textvariable=self._api_key_var,
            show="•",
            bg=ENTRY_BG, fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            font=("Helvetica", 12),
            bd=0,
        )
        self._key_entry.pack(fill=tk.X, ipady=8, padx=2)
        tk.Frame(key_frame, bg=ACCENT, height=2).pack(fill=tk.X)

        show_btn = tk.Button(
            self.root,
            text="Show / Hide Key",
            bg=PANEL, fg=DIM,
            activebackground=ENTRY_BG, activeforeground=TEXT,
            relief=tk.FLAT,
            font=("Helvetica", 9),
            cursor="hand2",
            command=self._toggle_key_visibility,
        )
        show_btn.pack(anchor="e", padx=28, pady=(0, 16))

        # ── Transcription Engine ───────────────────────────────────────────────
        self._section_label("Transcription Engine")

        self._engine_var = tk.StringVar(value=self.cfg.get("transcription_engine", "whisper-api"))
        engine_frame = tk.Frame(self.root, bg=BG)
        engine_frame.pack(fill=tk.X, **pad, pady=(0, 16))

        for val, label in [
            ("whisper-api", "OpenAI Whisper API  (cloud, accurate)"),
            ("faster-whisper", "faster-whisper  (local, offline, requires model download)"),
        ]:
            rb = tk.Radiobutton(
                engine_frame,
                text=label,
                variable=self._engine_var,
                value=val,
                bg=BG, fg=TEXT,
                activebackground=BG, activeforeground=ACCENT,
                selectcolor=ENTRY_BG,
                font=("Helvetica", 11),
                anchor="w",
            )
            rb.pack(fill=tk.X, pady=2)

        # ── Overlay Opacity ────────────────────────────────────────────────────
        self._section_label("Overlay Opacity")

        opacity_frame = tk.Frame(self.root, bg=BG)
        opacity_frame.pack(fill=tk.X, **pad, pady=(0, 24))

        self._opacity_var = tk.DoubleVar(value=self.cfg.get("overlay_opacity", 0.92))
        self._opacity_label = tk.Label(
            opacity_frame,
            text=f"{self._opacity_var.get():.0%}",
            bg=BG, fg=ACCENT,
            font=("Helvetica", 11, "bold"),
            width=5,
        )
        self._opacity_label.pack(side=tk.RIGHT)

        scale = tk.Scale(
            opacity_frame,
            from_=0.3, to=1.0,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            variable=self._opacity_var,
            bg=BG, fg=TEXT,
            troughcolor=ENTRY_BG,
            activebackground=ACCENT,
            highlightthickness=0,
            showvalue=False,
            command=lambda v: self._opacity_label.configure(text=f"{float(v):.0%}"),
        )
        scale.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 8))

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X, **pad, pady=(0, 16))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill=tk.X, **pad)

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            bg=PANEL, fg=DIM,
            activebackground=ENTRY_BG, activeforeground=TEXT,
            relief=tk.FLAT,
            font=("Helvetica", 12),
            cursor="hand2",
            padx=20, pady=8,
            command=self._cancel,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        save_btn = tk.Button(
            btn_frame,
            text="Save & Launch",
            bg=BTN_BG, fg=BTN_FG,
            activebackground="#9b8de8", activeforeground=BTN_FG,
            relief=tk.FLAT,
            font=("Helvetica", 12, "bold"),
            cursor="hand2",
            padx=20, pady=8,
            command=self._save,
        )
        save_btn.pack(side=tk.RIGHT)

        self.root.bind("<Return>", lambda e: self._save())
        self.root.bind("<Escape>", lambda e: self._cancel())

    def _section_label(self, text: str) -> None:
        tk.Label(
            self.root, text=text,
            bg=BG, fg=DIM,
            font=("Helvetica", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=28, pady=(0, 6))

    def _toggle_key_visibility(self) -> None:
        current = self._key_entry.cget("show")
        self._key_entry.configure(show="" if current else "•")

    def _save(self) -> None:
        key = self._api_key_var.get().strip()
        if not key:
            messagebox.showerror(
                "Missing API Key",
                "Please enter your OpenAI API key to continue.",
                parent=self.root,
            )
            return

        self.cfg["openai_api_key"] = key
        self.cfg["transcription_engine"] = self._engine_var.get()
        self.cfg["overlay_opacity"] = round(float(self._opacity_var.get()), 2)
        self.result = self.cfg
        self.root.destroy()

    def _cancel(self) -> None:
        self.root.destroy()

    def run(self) -> dict | None:
        """Show the dialog and return updated config, or None if cancelled."""
        self.root.mainloop()
        return self.result
