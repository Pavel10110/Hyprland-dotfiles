#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
WAL="$HOME/.cache/wal/colors.sh"
EWW_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/vexa/eww"
mkdir -p "$EWW_DIR"
cp "$BASE_DIR/eww/eww.yuck" "$EWW_DIR/eww.yuck"
OUT="$EWW_DIR/eww.scss"
BG="#041231"
FG="#c1c7c6"
ACCENT="#61A4D2"
ACCENT2="#DEAC73"

if [ -r "$WAL" ]; then
  set +u
  source "$WAL"
  set -u
  BG="${background:-$BG}"
  FG="${foreground:-$FG}"
  ACCENT="${color6:-$ACCENT}"
  ACCENT2="${color2:-$ACCENT2}"
fi

cat > "$OUT" <<CSS
\$bg: $BG;
\$fg: $FG;
\$accent: $ACCENT;
\$accent2: $ACCENT2;

* {
  all: unset;
  font-family: monospace;
}

.vexa-shell {
  background-color: rgba(red(\$bg), green(\$bg), blue(\$bg), 0.42);
  border: 1px solid rgba(red(\$accent), green(\$accent), blue(\$accent), 0.70);
  border-radius: 18px;
  padding: 0 6px;
  min-height: 38px;
  box-shadow: none;
}

.vexa-wave-wrap {
  margin: 0;
}

.vexa-bar-slot {
  min-width: 12px;
}

.vexa-text-wrap {
  min-width: 92px;
}

.vexa-text {
  color: \$fg;
  font-size: 12px;
  font-weight: 700;
}

.vexa-bar {
  color: \$accent;
  font-size: 18px;
  font-weight: 700;
  min-width: 0;
}
CSS
