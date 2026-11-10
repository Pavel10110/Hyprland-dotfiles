#!/usr/bin/env bash
set -euo pipefail
mapfile -d '' wallpapers < <(find "$HOME/Pictures/wallpapers" -type f -print0 | sort -z)
((${#wallpapers[@]})) || { printf 'No wallpapers found\n' >&2; exit 1; }
last=''
if [[ -f "$HOME/.last_wallpaper" ]]; then last=$(<"$HOME/.last_wallpaper"); fi
next=0
for i in "${!wallpapers[@]}"; do
  if [[ ${wallpapers[$i]} == "$last" ]]; then next=$(( (i+1) % ${#wallpapers[@]} )); break; fi
done
wallpaper=${wallpapers[$next]}
awww img "$wallpaper" --transition-type grow --transition-duration 1
printf '%s\n' "$wallpaper" > "$HOME/.last_wallpaper"
wal -i "$wallpaper"
hyprctl reload
pkill -x waybar || true
waybar >"$XDG_RUNTIME_DIR/waybar-wallpaper.log" 2>&1 &
if command -v pywalfox >/dev/null; then pywalfox update || true; fi
if command -v walogram >/dev/null; then walogram || true; fi
magick "$wallpaper" -resize 800x300 "$HOME/.cache/rofi_wallpaper_small.jpg"
# Existing Rofi theme already references this stable cache filename.
swaync-client -rs || true
