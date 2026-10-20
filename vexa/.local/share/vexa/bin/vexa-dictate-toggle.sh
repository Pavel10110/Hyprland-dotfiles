#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$SCRIPT_DIR"
MODEL="$BASE_DIR/models/ggml-small.bin"
EWW_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/vexa/eww"
COLORS_SCRIPT="$BIN_DIR/vexa-eww-colors.sh"
METER_SCRIPT="$BIN_DIR/vexa-eww-level-meter.py"
DIR="/tmp/vexa-dictation-${UID}"
PID="$DIR/record.pid"
METER_PID="$DIR/level-meter.pid"
RAW="$DIR/raw.wav"
WAV="$DIR/clean.wav"
OUT="$DIR/out.txt"
LOG="$DIR/log.txt"
METER_LOG="$DIR/level-meter.log"
mkdir -p "$DIR"

notify() {
  command -v notify-send >/dev/null 2>&1 || return 0
  notify-send "Vexa dictation" "$1" >/dev/null 2>&1 || true
}

ensure_session_env() {
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$UID}"
  export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

  if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -d "$XDG_RUNTIME_DIR" ]; then
    local sock
    sock="$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'wayland-*' 2>/dev/null | head -n 1 || true)"
    if [ -n "$sock" ]; then
      export WAYLAND_DISPLAY="$(basename "$sock")"
    fi
  fi

  if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && [ -d "$XDG_RUNTIME_DIR/hypr" ]; then
    local inst
    inst="$(find "$XDG_RUNTIME_DIR/hypr" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1 || true)"
    if [ -n "$inst" ]; then
      export HYPRLAND_INSTANCE_SIGNATURE="$(basename "$inst")"
    fi
  fi
}

find_whisper() {
  command -v whisper-cli 2>/dev/null \
    || command -v whisper-cpp-cli 2>/dev/null \
    || command -v whisper-cpp 2>/dev/null \
    || command -v whisper 2>/dev/null \
    || true
}

detect_whisper_threads() {
  local n
  n="${VEXA_WHISPER_THREADS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)}"
  case "$n" in
    ''|*[!0-9]*) n=4 ;;
  esac
  if [ "$n" -lt 1 ]; then
    n=4
  fi
  printf '%s\n' "$n"
}

eww_cmd() {
  eww --force-wayland -c "$EWW_DIR" "$@"
}

focused_monitor() {
  ensure_session_env
  if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || ! command -v hyprctl >/dev/null 2>&1; then
    return 0
  fi
  local monitors
  monitors="$(hyprctl monitors -j 2>/dev/null || true)"
  [ -n "$monitors" ] || return 0
  python3 - <<'PY' "$monitors"
import json, sys
try:
    monitors = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
focused = next((m for m in monitors if m.get("focused")), None)
if focused and focused.get("id") is not None:
    print(focused["id"])
elif monitors and monitors[0].get("id") is not None:
    print(monitors[0]["id"])
PY
}

start_eww() {
  ensure_session_env
  [ -x "$COLORS_SCRIPT" ] && "$COLORS_SCRIPT" >/dev/null 2>&1 || true
  [ -d "$EWW_DIR" ] || return 1
  if ! eww_cmd ping >/dev/null 2>&1; then
    eww_cmd daemon >/dev/null 2>&1 || true
    sleep 0.15
  fi
  eww_cmd reload >/dev/null 2>&1 || true
}

close_meter() {
  if [ -s "$METER_PID" ]; then
    kill "$(cat "$METER_PID")" >/dev/null 2>&1 || true
    rm -f "$METER_PID"
  fi
}

close_bubble() {
  close_meter
  eww_cmd close vexa-listening vexa-transcribing >/dev/null 2>&1 || true
}

open_window() {
  local window="$1"
  local screen="${2:-}"
  if [ -n "$screen" ]; then
    eww_cmd open "$window" --screen "$screen" >/dev/null 2>&1 || eww_cmd open "$window" >/dev/null 2>&1 || true
  else
    eww_cmd open "$window" >/dev/null 2>&1 || true
  fi
}

show_transcribing() {
  local text="$1"
  ensure_session_env
  start_eww || return 0
  close_bubble
  eww_cmd update "vexa_text=$text" >/dev/null 2>&1 || true
  open_window vexa-transcribing "$(focused_monitor)"
}

show_listening() {
  ensure_session_env
  start_eww || return 0
  close_bubble
  eww_cmd update vexa_b1=▁ vexa_b2=▁ vexa_b3=▁ vexa_b4=▁ vexa_b5=▁ >/dev/null 2>&1 || true
  open_window vexa-listening "$(focused_monitor)"
  if command -v parec >/dev/null 2>&1 && [ -x "$METER_SCRIPT" ]; then
    : >"$METER_LOG"
    python3 "$METER_SCRIPT" --config "$EWW_DIR" >>"$METER_LOG" 2>&1 &
    echo $! > "$METER_PID"
  fi
}

fail() {
  close_bubble
  notify "$1"
  echo "$1" >&2
  exit 1
}

[ -s "$MODEL" ] || fail "Model missing: $MODEL"
WHISPER_BIN="$(find_whisper)"
[ -n "$WHISPER_BIN" ] || fail "Whisper CLI missing"
WHISPER_THREADS="$(detect_whisper_threads)"
command -v pw-record >/dev/null 2>&1 || fail "pw-record missing"
command -v ffmpeg >/dev/null 2>&1 || fail "ffmpeg missing"
command -v wl-copy >/dev/null 2>&1 || fail "wl-copy missing"
command -v wtype >/dev/null 2>&1 || fail "wtype missing"
command -v eww >/dev/null 2>&1 || fail "eww missing"

if [ -s "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
  REC_PID="$(cat "$PID")"
  kill -INT "$REC_PID" 2>/dev/null || kill "$REC_PID" 2>/dev/null || true
  for _ in $(seq 1 40); do
    kill -0 "$REC_PID" 2>/dev/null || break
    sleep 0.1
  done
  rm -f "$PID"

  show_transcribing "Transcribing..."

  ffmpeg -y -loglevel error -i "$RAW" -ar 16000 -ac 1 -c:a pcm_s16le "$WAV" || fail "Audio convert failed"
  printf 'whisper_bin=%s\nwhisper_threads=%s\nmodel=%s\n' "$WHISPER_BIN" "$WHISPER_THREADS" "$MODEL" > "$LOG"
  "$WHISPER_BIN" -t "$WHISPER_THREADS" -m "$MODEL" -f "$WAV" -l auto -nt -np > "$OUT" 2>> "$LOG" || fail "Whisper failed"

  TEXT="$(tr '\n' ' ' < "$OUT" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
  if [ -z "$TEXT" ]; then
    close_bubble
    notify "No speech detected"
    exit 0
  fi

  printf "%s" "$TEXT" | wl-copy || true
  if ! wtype -M ctrl -P v -p v -m ctrl 2>/dev/null; then
    wtype "$TEXT" 2>/dev/null || true
  fi
  close_bubble
  notify "Pasted"
else
  rm -f "$RAW" "$WAV" "$OUT" "$LOG"
  show_listening
  pw-record --rate 16000 --channels 1 "$RAW" >/dev/null 2>"$LOG" &
  echo $! > "$PID"
fi
