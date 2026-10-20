#!/usr/bin/env bash
set -euo pipefail

TITLE="Vexa Whisper Status"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
MODEL="$BASE_DIR/models/ggml-small.bin"
WHISPER_CLI="$(command -v whisper-cli || true)"
MSG="Super+V now uses the fixed toggle dictation flow."

if [ ! -s "$MODEL" ]; then
  MSG="$MSG\nModel missing: $MODEL"
elif [ -z "$WHISPER_CLI" ]; then
  MSG="$MSG\nwhisper-cli is not installed."
else
  MSG="$MSG\nModel: OK\nCLI: $WHISPER_CLI"
fi

CMD="printf '%b\n\nPress Enter to close...' \"$MSG\"; read -r _"
if command -v ghostty >/dev/null 2>&1; then
  exec ghostty --title="$TITLE" -e bash -lc "$CMD"
elif command -v kitty >/dev/null 2>&1; then
  exec kitty --title "$TITLE" bash -lc "$CMD"
elif command -v foot >/dev/null 2>&1; then
  exec foot --title="$TITLE" bash -lc "$CMD"
else
  exec bash -lc "$CMD"
fi
