#!/usr/bin/env bash
# install.sh — One-shot installer for MeetAssist
# Run this script ONCE before starting the app.
# Usage:  bash install.sh

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✦ MeetAssist — Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

OS="$(uname -s)"

# ── System dependencies ───────────────────────────────────────────────────────
if [ "$OS" = "Linux" ]; then
    echo "[1/3] Installing system dependencies (portaudio, tkinter)…"
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y portaudio19-dev python3-tk
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y portaudio-devel python3-tkinter
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm portaudio tk
    else
        echo "  ⚠ Unknown package manager. Please install: portaudio19-dev python3-tk"
    fi
elif [ "$OS" = "Darwin" ]; then
    echo "[1/3] Installing system dependencies (portaudio)…"
    if command -v brew &>/dev/null; then
        brew install portaudio
    else
        echo "  ⚠ Homebrew not found. Install from https://brew.sh then run: brew install portaudio"
    fi
fi

# ── Python dependencies ────────────────────────────────────────────────────────
echo "[2/3] Installing Python packages…"
pip install --upgrade pip -q
pip install -r requirements.txt

# ── Optional: faster-whisper ──────────────────────────────────────────────────
echo ""
read -r -p "Install faster-whisper (local offline transcription)? [y/N] " REPLY
if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    pip install faster-whisper
    echo "  ✓ faster-whisper installed."
fi

# ── Create app dir ─────────────────────────────────────────────────────────────
echo "[3/3] Creating app directory (~/.meetassist)…"
mkdir -p ~/.meetassist
echo "  ✓ ~/.meetassist ready."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✓ Installation complete!"
echo " Run:  python main.py"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
