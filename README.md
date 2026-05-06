# ✦ MeetAssist — Invisible AI Meeting Assistant

An always-on-top floating overlay that silently listens to your Google Meet (or any meeting), transcribes speech in real-time, and streams GPT-4o answers **only you can see** — invisible to screen sharing.

---

## Features

| Feature | Details |
|---|---|
| 🎙️ Audio capture | System loopback (speakers) + optional mic, 3-second chunks |
| 📝 Transcription | OpenAI Whisper API or local `faster-whisper` |
| 🤖 AI Answers | GPT-4o with streaming, ≤3 bullet points |
| 🕵️ Invisible overlay | Excluded from screen capture (platform-specific) |
| 🖥️ Always on top | Frameless, draggable, dark glass-morphism UI |
| ⌨️ Global hotkeys | Toggle, Ask, Clear, Quit — work even when window is hidden |
| 🗃️ SQLite logging | Every transcript chunk and AI answer saved locally |
| ⚙️ Config file | `~/.meetassist/config.json` — persisted between runs |

---

## Project Structure

```
meetassist/
├── main.py            # Entry point & app orchestrator
├── overlay.py         # Tkinter floating overlay window
├── audio_capture.py   # Loopback / mic audio streaming
├── transcription.py   # Whisper transcription engine + rolling buffer
├── ai_assistant.py    # GPT-4o streaming answer generator
├── hotkeys.py         # Global hotkey manager
├── database.py        # SQLite persistence (sessions, transcripts, answers)
├── config.py          # Config load/save (~/.meetassist/config.json)
├── setup_dialog.py    # First-run API key setup dialog
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- `pip` (or `pipx`)
- An [OpenAI API key](https://platform.openai.com/api-keys)

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `tkinter` is part of Python's standard library. On Ubuntu/Debian, install it with:
> ```bash
> sudo apt install python3-tk
> ```

### 3. Run

```bash
python main.py
```

On first launch a setup dialog will appear. Enter your OpenAI API key and click **Save & Launch**.

---

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+Shift+H` | Toggle overlay show/hide |
| `Ctrl+Shift+A` | Manually ask AI with current transcript |
| `Ctrl+Shift+C` | Clear overlay and reset transcript context |
| `Ctrl+Shift+Q` | Quit MeetAssist |

All hotkeys are configurable in `~/.meetassist/config.json`.

---

## Audio Loopback Setup

MeetAssist listens to **system audio output** (what plays through your speakers — i.e. remote participants' voices). This requires a loopback audio device.

### 🪟 Windows — Enable Stereo Mix

1. Right-click the speaker icon in the taskbar → **Sounds**
2. Go to the **Recording** tab
3. Right-click on empty area → **Show Disabled Devices**
4. Right-click **Stereo Mix** → **Enable**
5. Right-click **Stereo Mix** → **Set as Default Device**

Alternatively, use a **WASAPI loopback** device — MeetAssist auto-detects it by scanning `sounddevice` for devices containing "loopback" or "stereo mix" in the name.

### 🍎 macOS — BlackHole Virtual Audio Device

1. Install [BlackHole](https://existential.audio/blackhole/) (2ch is free):
   ```bash
   brew install blackhole-2ch
   ```
2. Open **Audio MIDI Setup** → create a **Multi-Output Device** combining your speakers + BlackHole
3. Set that Multi-Output Device as your system output
4. In MeetAssist config, set the loopback device name to `BlackHole 2ch`

### 🐧 Linux — PulseAudio / PipeWire Monitor Source

Most Linux systems expose a **monitor source** automatically. MeetAssist auto-detects it by looking for `monitor` in the device name.

To verify:
```bash
python -c "import sounddevice as sd; [print(i, d['name']) for i, d in enumerate(sd.query_devices())]"
```

Look for a device like `pulse` or `Monitor of Built-in Audio Analog Stereo`. PipeWire users may need:
```bash
# Create a loopback module
pactl load-module module-loopback
```

---

## Screen Capture Exclusion

### Windows ✅ (Full support)
MeetAssist calls `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` via ctypes. The overlay is **completely invisible** to all screen capture APIs, including Google Meet's built-in sharing and OBS.

> Requires Windows 10 version 2004+ (build 19041+). Run as a normal user — no elevation needed.

### macOS ⚠️ (Partial)
Full exclusion requires the Accessibility API or a signed helper. MeetAssist attempts it via AppKit's `NSWindowSharingNone`. If that fails, it falls back to an osascript approach.

For guaranteed exclusion on macOS, run in a separate macOS user account not being screen-shared.

### Linux ⚠️ (Best-effort)
X11 has no standard API to exclude windows from capture. MeetAssist sets `_NET_WM_BYPASS_COMPOSITOR` and `override_redirect` which hides the window from most WM window lists.

**Workaround:** Use a separate virtual desktop / workspace. Google Meet only shares the active desktop.

---

## Configuration

Config is stored at `~/.meetassist/config.json`. Edit it directly or use the setup dialog (delete the API key to trigger it again on next launch).

```json
{
  "openai_api_key": "sk-...",
  "transcription_engine": "whisper-api",
  "hotkey_toggle": "ctrl+shift+h",
  "hotkey_ask": "ctrl+shift+a",
  "hotkey_clear": "ctrl+shift+c",
  "hotkey_quit": "ctrl+shift+q",
  "overlay_opacity": 0.92,
  "overlay_font_size": 14,
  "overlay_width": 480,
  "overlay_height": 340,
  "overlay_x": 40,
  "overlay_y": 40,
  "model": "gpt-4o"
}
```

### Transcription Engine Options

| Value | Description |
|---|---|
| `"whisper-api"` | OpenAI cloud API — most accurate, costs ~$0.006/min |
| `"faster-whisper"` | Fully local, offline. Requires: `pip install faster-whisper` |

---

## Local Transcription (faster-whisper)

```bash
pip install faster-whisper
```

Then in `config.json`, set `"transcription_engine": "faster-whisper"`.

Available model sizes: `tiny`, `base`, `small`, `medium`, `large-v3`  
First run downloads the model to `~/.cache/huggingface/`.

---

## Database

SQLite database at `~/.meetassist/sessions.db`.

```sql
-- View recent answers
SELECT timestamp, answer FROM answers ORDER BY id DESC LIMIT 10;

-- Export a session transcript
SELECT timestamp, speaker, text FROM transcripts WHERE session_id = 1;
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No audio captured | Check loopback device setup (see Audio section above) |
| `keyboard` errors on Linux | Run with `sudo python main.py` (keyboard lib needs root for global hooks) |
| Overlay flickers | Disable compositor transparency effects in your DE settings |
| Whisper API 429 error | You've hit rate limits; switch to `faster-whisper` locally |
| `ModuleNotFoundError: tkinter` | `sudo apt install python3-tk` |

---

## Privacy

- All audio processing happens locally except Whisper API calls (sent to OpenAI)
- Transcripts and answers are stored in `~/.meetassist/sessions.db` — never sent anywhere else
- Use `faster-whisper` for fully offline, zero-cloud operation

---

## License

MIT — free to use, modify, and distribute.
