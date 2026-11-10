#!/usr/bin/env bash
set -euo pipefail

# Hyprland exec children may share the compositor's background terminal group.
# Never read its terminal: SIGTTIN would stop the entire desktop group.
exec </dev/null

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$SCRIPT_DIR"
# Optional host tuning, owned by the desktop user. Never source another user's home.
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/vexa/dictation.conf"
[ ! -f "$CONFIG" ] || source "$CONFIG"
MODEL="${VEXA_WHISPER_MODEL:-$BASE_DIR/models/ggml-small.bin}"
FILE_MODE=0
INPUT=""
OUTPUT=""
CANCEL=0
case "${1:-}" in
  --transcribe-file)
    [ "$#" -eq 4 ] && [ "$3" = --output ] || { echo 'Usage: --transcribe-file INPUT --output OUTPUT' >&2; exit 2; }
    FILE_MODE=1; INPUT="$2"; OUTPUT="$4" ;;
  --cancel) CANCEL=1 ;;
  '') ;;
  *) echo 'Unknown argument' >&2; exit 2 ;;
esac
# File mode MUST remain isolated: no microphone, clipboard, UI or live state.
if [ "$FILE_MODE" = 1 ]; then
  VEXA_DICTATION_UI=0
  VEXA_DICTATION_NO_PASTE=1
fi
EWW_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/vexa/eww"
COLORS_SCRIPT="$BIN_DIR/vexa-eww-colors.sh"
METER_SCRIPT="$BIN_DIR/vexa-eww-level-meter.py"
umask 077
if [ "$FILE_MODE" = 1 ]; then
  DIR="$(mktemp -d "${TMPDIR:-${XDG_RUNTIME_DIR:-/tmp}}/vexa-file.XXXXXXXX")"
  trap 'rm -rf -- "$DIR"' EXIT
else
  DIR="${VEXA_DICTATION_STATE_DIR:-${XDG_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}/vexa-dictation}"
fi
[ ! -L "$DIR" ] || { echo 'Refusing symlink state directory' >&2; exit 1; }
mkdir -p -- "$DIR"
[ -O "$DIR" ] || { echo 'State directory not owned by current user' >&2; exit 1; }
chmod 700 -- "$DIR"
exec 9>"$DIR/toggle.lock"
flock -w 10 9 || { echo 'Dictation busy' >&2; exit 1; }
PID="$DIR/record.pid"
METER_PID="$DIR/level-meter.pid"
RAW="$DIR/raw.wav"
WAV="$DIR/clean.wav"
OUT="$DIR/out.txt"
LOG="$DIR/log.txt"
METER_LOG="$DIR/level-meter.log"
mkdir -p "$DIR"

notify() {
  [ "${VEXA_DICTATION_UI:-1}" != 0 ] || return 0
  command -v notify-send >/dev/null 2>&1 || return 0
  notify-send "Vexa dictation" "$1" 9>&- >/dev/null 2>&1 || true
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
  if [ -n "${VEXA_WHISPER_BIN:-}" ]; then
    command -v "$VEXA_WHISPER_BIN"; return
  fi
  command -v whisper-cli 2>/dev/null \
    || command -v whisper-cpp-cli 2>/dev/null \
    || command -v whisper-cpp 2>/dev/null \
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
  eww --force-wayland -c "$EWW_DIR" "$@" 9>&-
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
  [ "${VEXA_DICTATION_UI:-1}" != 0 ] || return 1
  command -v eww >/dev/null 2>&1 || return 1
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
  stop_owned "$METER_PID" TERM || true
}

close_bubble() {
  close_meter
  [ "${VEXA_DICTATION_UI:-1}" != 0 ] || return 0
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
    python3 "$METER_SCRIPT" --config "$EWW_DIR" 9>&- >>"$METER_LOG" 2>&1 &
    save_pid "$METER_PID" "$!"
  fi
}

fail() {
  close_bubble
  notify "$1"
  echo "$1" >&2
  exit 1
}

# Store Linux start-time alongside PID. A stale/recycled PID is never signalled.
proc_token() {
  local stat rest
  [ -r "/proc/$1/stat" ] || return 1
  stat="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
  rest="${stat##*) }"
  [ "${rest%% *}" != Z ] || return 1
  awk '{print $20}' <<< "$rest"
}
save_pid() {
  local token
  token="$(proc_token "$2")" || return 1
  printf '%s %s\n' "$2" "$token" > "$1"
}
owned_pid() {
  local p token current
  [ -s "$1" ] || return 1
  read -r p token < "$1" || return 1
  [[ "$p" =~ ^[0-9]+$ && "${token:-}" =~ ^[0-9]+$ ]] || return 1
  [ "$p" -gt 1 ] || return 1
  current="$(proc_token "$p")" || return 1
  [ "$current" = "$token" ] || return 1
  printf '%s\n' "$p"
}
stop_owned() {
  local p i
  p="$(owned_pid "$1")" || { rm -f -- "$1"; return 0; }
  kill -"$2" "$p" 2>/dev/null || true
  for ((i=0; i<40; i++)); do
    owned_pid "$1" >/dev/null || break
    sleep 0.1
  done
  # Only signal a positively revalidated child, never its desktop process group.
  if owned_pid "$1" >/dev/null; then
    kill -TERM "$p" 2>/dev/null || true
    sleep 0.2
  fi
  if owned_pid "$1" >/dev/null; then
    kill -KILL "$p" 2>/dev/null || true
    sleep 0.1
  fi
  if owned_pid "$1" >/dev/null; then return 1; fi
  rm -f -- "$1"
}

if [ "$CANCEL" = 1 ]; then
  stop_owned "$PID" INT || fail 'Recorder would not stop'
  close_bubble
  exit 0
fi

[ -r "$MODEL" ] && [ -s "$MODEL" ] || fail "Model missing: $MODEL"
WHISPER_BIN="$(find_whisper)" || fail 'Whisper CLI missing'
[ -n "$WHISPER_BIN" ] || fail "Whisper CLI missing"
WHISPER_THREADS="$(detect_whisper_threads)"
command -v ffmpeg >/dev/null 2>&1 || fail "ffmpeg missing"
command -v timeout >/dev/null 2>&1 || fail "timeout missing"
BACKEND_ARGS=()
case "${VEXA_WHISPER_BACKEND:-auto}" in
  auto) ;;
  cpu) BACKEND_ARGS=(-ng) ;;
  *) fail 'Invalid VEXA_WHISPER_BACKEND (auto or cpu)' ;;
esac
for duration in "${VEXA_WHISPER_TIMEOUT:-120}" "${VEXA_CONVERT_TIMEOUT:-20}"; do
  [[ "$duration" =~ ^[1-9][0-9]*$ ]] || fail 'Timeout must be a positive integer in seconds'
done

transcribe() {
  printf 'whisper_bin=%s\nwhisper_threads=%s\nmodel=%s\nbackend=%s\n' "$WHISPER_BIN" "$WHISPER_THREADS" "$MODEL" "${VEXA_WHISPER_BACKEND:-auto}" > "$LOG"
  timeout -k 2 "${VEXA_CONVERT_TIMEOUT:-20}" ffmpeg -nostdin -y -loglevel error -i "$1" -ar 16000 -ac 1 -c:a pcm_s16le "$WAV" </dev/null 2>>"$LOG" || fail "Audio convert failed (see $LOG)"
  timeout -k 2 "${VEXA_WHISPER_TIMEOUT:-120}" "$WHISPER_BIN" -t "$WHISPER_THREADS" "${BACKEND_ARGS[@]}" -m "$MODEL" -f "$WAV" -l "${VEXA_WHISPER_LANGUAGE:-auto}" -nt -np </dev/null > "$DIR/transcript.tmp" 2>> "$LOG" || fail "Whisper failed or timed out (see $LOG)"
  TEXT="$(tr '\n' ' ' < "$DIR/transcript.tmp" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
  printf '%s\n' "$TEXT" > "$OUT"
  rm -f "$DIR/transcript.tmp"
}

if [ "$FILE_MODE" = 1 ]; then
  [ -f "$INPUT" ] || fail 'Input audio missing'
  # Keep diagnostics next to the explicitly requested output, never print a transcript.
  LOG="$OUTPUT.log"
  transcribe "$INPUT"
  cp -- "$OUT" "$OUTPUT"
  exit 0
fi

if [ "${VEXA_DICTATION_NO_PASTE:-0}" != 1 ]; then
  command -v wl-copy >/dev/null 2>&1 || fail "wl-copy missing"
  command -v wtype >/dev/null 2>&1 || fail "wtype missing"
fi
if owned_pid "$PID" >/dev/null; then
  stop_owned "$PID" INT || fail 'Recorder would not stop'
  show_transcribing "Transcribing..."
  transcribe "$RAW"
  if [ -z "$TEXT" ]; then
    close_bubble
    notify "No speech detected"
    exit 0
  fi
  if [ "${VEXA_DICTATION_NO_PASTE:-0}" != 1 ]; then
    # Do not paste a stale clipboard if wl-copy failed. -- handles leading '-'.
    printf '%s' "$TEXT" | wl-copy || fail 'Clipboard write failed'
    if ! wtype -M ctrl -P v -p v -m ctrl 2>/dev/null; then
      wtype -- "$TEXT" 2>/dev/null || fail 'Text input failed'
    fi
    notify "Pasted"
  fi
  close_bubble
else
  rm -f "$PID" "$RAW" "$WAV" "$OUT" "$LOG"
  command -v pw-record >/dev/null 2>&1 || fail "pw-record missing"
  ensure_session_env
  show_listening
  RECORD_ARGS=()
  [ -z "${VEXA_DICTATION_SOURCE:-}" ] || RECORD_ARGS=(--target "$VEXA_DICTATION_SOURCE")
  pw-record --rate 16000 --channels 1 "${RECORD_ARGS[@]}" "$RAW" 9>&- </dev/null >/dev/null 2>"$LOG" &
  rec=$!
  save_pid "$PID" "$rec" || fail 'Recorder failed to start'
  sleep 0.15
  owned_pid "$PID" >/dev/null || { rm -f "$PID"; fail "Recorder exited (see $LOG)"; }
fi
