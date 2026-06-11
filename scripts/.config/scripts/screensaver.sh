#!/bin/bash

# 1. Loop through monitors
for MON in $(hyprctl monitors -j | jq -r '.[] .name'); do
  # 2. Launch Ghostty on the specific monitor
  # We use the argument inside ghostty to position it, or rely on Hyprland default placement
  # Since we have specific window rules, we just need to launch it.
  
  # NOTE: We use '&' to run in background so the loop continues instantly
  hyprctl dispatch exec "[monitor $MON] ghostty --class=bonsai -e cbonsai -l -t 0.5 -i -C -W -L 150"
  
  sleep 0.2
done
