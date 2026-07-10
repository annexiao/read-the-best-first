#!/usr/bin/env bash
set -euo pipefail

# Read the Best First — first-time setup
# Usage: ./setup.sh

echo "=== Read the Best First: setup ==="

command -v brew >/dev/null 2>&1 || { echo "Error: Homebrew is required (https://brew.sh)."; exit 1; }

# --- Homebrew deps (idempotent: brew install is a no-op if already installed) ---
for pkg in espeak-ng ffmpeg python@3.12 atomicparsley mp4v2; do
  if brew list "$pkg" >/dev/null 2>&1; then
    echo "OK: $pkg already installed"
  else
    echo "Installing $pkg..."
    brew install "$pkg"
  fi
done

# --- Resolve a python3.12 interpreter (brew-installed or already on PATH) ---
PYTHON312="$(command -v python3.12 || true)"
if [ -z "$PYTHON312" ]; then
  BREW_PREFIX="$(brew --prefix python@3.12 2>/dev/null || true)"
  if [ -n "$BREW_PREFIX" ] && [ -x "$BREW_PREFIX/bin/python3.12" ]; then
    PYTHON312="$BREW_PREFIX/bin/python3.12"
  fi
fi
if [ -z "$PYTHON312" ]; then
  echo "Error: could not find a python3.12 interpreter after brew install. Check your PATH."
  exit 1
fi
echo "Using python3.12: $PYTHON312"

# --- Virtualenv (idempotent: skip if already created) ---
if [ ! -d .venv ]; then
  echo "Creating .venv..."
  "$PYTHON312" -m venv .venv
else
  echo "OK: .venv already exists"
fi

# --- Python dependencies ---
echo "Installing Python dependencies into .venv..."
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install "kokoro>=0.9.4" soundfile numpy ebooklib beautifulsoup4 trafilatura pyyaml

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Open this repo in Claude Code (or any agent that reads skills) and say what"
echo "     you want, e.g. \"turn this blog into a ranked audiobook\"."
echo "  2. Before ranking anything, edit the rubric in"
echo "     skills/curated-epub-audiobook/SKILL.md (\"The rubric\" section) — it's personal."
echo "  3. Build an EPUB:  .venv/bin/python scripts/build_epub.py manifest.json --out book.epub"
echo "  4. Voice-check 3 chapters before a full audiobook run:"
echo "     .venv/bin/python scripts/epub2m4b.py book.epub --limit 3 --device mps"
echo "  5. Using Claude Code? CLAUDE.md has the full map of skills and scripts."
echo ""
echo "Note: first synthesis auto-downloads Kokoro-82M weights (~330 MB) and a spaCy model"
echo "      from Hugging Face into ~/.cache/huggingface — no account or token needed."
