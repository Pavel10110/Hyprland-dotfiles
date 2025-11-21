#!/bin/bash
LAYOUT=$(hyprctl devices -j | jq -r '.keyboards[0].active_keymap' | head -c2 | tr 'a-z' 'A-Z')
POS=$(hyprctl cursorpos -j)
X=$(echo "$POS" | jq '.x - 70' | cut -f1 -d.)
Y=$(echo "$POS" | jq '.y + 40' | cut -f1 -d.)

eww update text="$LAYOUT"
eww open layout_osd

# Wait + move (100% reliable)
sleep 0.08
ADDR=$(hyprctl clients -j | jq -r '.[] | select(.class == "Eww") | .address' | head -n1)
[ -n "$ADDR" ] && hyprctl dispatch movewindowpixel exact $X $Y,address:$ADDR

sleep 1.3 && eww close layout_osd &
