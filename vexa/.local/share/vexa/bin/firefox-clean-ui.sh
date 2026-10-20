#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-apply}"
PROFILE_ROOT="${HOME}/.mozilla/firefox"
PROFILES_INI="${PROFILE_ROOT}/profiles.ini"
IMPORT_LINE='@import url("vexa-clean-ui.css"); /* vexa-clean-ui */'
CSS_MARKER='vexa-clean-ui'
PREF_LINE='user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
TS="$(date +%Y%m%d-%H%M%S)"

notify() {
  local msg="$1"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Firefox clean UI" "$msg" || true
  fi
  printf '%s\n' "$msg"
}

find_profile() {
  if [[ ! -f "$PROFILES_INI" ]]; then
    return 1
  fi
  python3 - "$PROFILES_INI" <<'PY'
import configparser, os, sys
ini = sys.argv[1]
cp = configparser.RawConfigParser()
cp.read(ini)
chosen = None
for sec in cp.sections():
    if sec.startswith("Profile") and cp.get(sec, "Default", fallback="0") == "1":
        chosen = sec
        break
if chosen is None:
    for sec in cp.sections():
        if sec.startswith("Profile"):
            chosen = sec
            break
if chosen is None:
    raise SystemExit(1)
path = cp.get(chosen, "Path")
if cp.get(chosen, "IsRelative", fallback="1") == "1":
    print(os.path.join(os.path.dirname(ini), path))
else:
    print(path)
PY
}

apply_mode() {
  local profile_dir="$1"
  local chrome_dir="$profile_dir/chrome"
  local userchrome="$chrome_dir/userChrome.css"
  local managed_css="$chrome_dir/vexa-clean-ui.css"
  local userjs="$profile_dir/user.js"

  mkdir -p "$chrome_dir"

  if [[ -f "$userchrome" && ! -f "$userchrome.bak-vexa-clean-ui" ]]; then
    cp -a "$userchrome" "$userchrome.bak-vexa-clean-ui"
  fi
  if [[ -f "$userjs" && ! -f "$userjs.bak-vexa-clean-ui" ]]; then
    cp -a "$userjs" "$userjs.bak-vexa-clean-ui"
  fi

  cat > "$managed_css" <<'CSS'
/* vexa-clean-ui */
#TabsToolbar,
#nav-bar,
#PersonalToolbar,
#toolbar-menubar,
#titlebar,
.titlebar-buttonbox-container,
#unified-extensions-button,
#sidebar-button {
  visibility: collapse !important;
  min-height: 0 !important;
  max-height: 0 !important;
}

#navigator-toolbox {
  border: none !important;
}

#main-window,
#browser,
#appcontent {
  margin: 0 !important;
  padding: 0 !important;
}
CSS

  if [[ -f "$userchrome" ]]; then
    if ! grep -Fq "$CSS_MARKER" "$userchrome"; then
      printf '\n%s\n' "$IMPORT_LINE" >> "$userchrome"
    fi
  else
    printf '%s\n' "$IMPORT_LINE" > "$userchrome"
  fi

  tmp_userjs="$(mktemp)"
  if [[ -f "$userjs" ]]; then
    grep -Fv 'toolkit.legacyUserProfileCustomizations.stylesheets' "$userjs" > "$tmp_userjs" || true
  fi
  printf '%s\n' "$PREF_LINE" >> "$tmp_userjs"
  mv "$tmp_userjs" "$userjs"

  if pgrep -x firefox >/dev/null 2>&1; then
    notify "Applied. Restart Firefox once to load the clean UI."
  else
    firefox >/dev/null 2>&1 & disown || true
    notify "Applied and launched Firefox with the clean UI."
  fi
}

restore_mode() {
  local profile_dir="$1"
  local chrome_dir="$profile_dir/chrome"
  local userchrome="$chrome_dir/userChrome.css"
  local managed_css="$chrome_dir/vexa-clean-ui.css"

  rm -f "$managed_css"

  if [[ -f "$userchrome" ]]; then
    tmp_userchrome="$(mktemp)"
    grep -Fv 'vexa-clean-ui.css' "$userchrome" > "$tmp_userchrome" || true
    mv "$tmp_userchrome" "$userchrome"
  fi

  notify "Clean UI import removed. Restart Firefox once to restore the normal UI."
}

profile_dir="$(find_profile || true)"
if [[ -z "$profile_dir" || ! -d "$profile_dir" ]]; then
  notify "Could not find a Firefox profile under ${PROFILE_ROOT}. Open Firefox once, then run this again."
  exit 1
fi

case "$ACTION" in
  apply)
    apply_mode "$profile_dir"
    ;;
  restore)
    restore_mode "$profile_dir"
    ;;
  *)
    printf 'Usage: %s [apply|restore]\n' "$0" >&2
    exit 2
    ;;
esac
