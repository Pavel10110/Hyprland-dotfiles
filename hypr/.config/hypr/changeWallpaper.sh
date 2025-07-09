#!/bin/bash

# Directory containing wallpapers
WALLPAPER_DIR="/home/archyper/Pictures/wallpapers/"
HISTORY_FILE="/home/archyper/.last_wallpaper"

# Get the list of wallpapers sorted alphabetically
WALLPAPERS=($(find "$WALLPAPER_DIR" -type f | sort))

# Check if wallpapers exist
if [[ ${#WALLPAPERS[@]} -eq 0 ]]; then
    echo "No wallpapers found in $WALLPAPER_DIR"
    exit 1
fi

# Read the last used wallpaper from history
if [[ -f "$HISTORY_FILE" ]]; then
    LAST_WALL=$(cat "$HISTORY_FILE")
else
    LAST_WALL=""
fi

# Find the index of the last used wallpaper
NEXT_INDEX=0
for i in "${!WALLPAPERS[@]}"; do
    if [[ "${WALLPAPERS[$i]}" == "$LAST_WALL" ]]; then
        NEXT_INDEX=$((i + 1))
        break
    fi
done

# Loop back to the first wallpaper if we reached the end
if [[ $NEXT_INDEX -ge ${#WALLPAPERS[@]} ]]; then
    NEXT_INDEX=0
fi

# Get the next wallpaper
WALLPAPER="${WALLPAPERS[$NEXT_INDEX]}"

# Save the selected wallpaper for next time
echo "$WALLPAPER" > "$HISTORY_FILE"

# Apply the wallpaper using Hyprpaper
#hyprctl hyprpaper preload "$WALLPAPER"
#hyprctl hyprpaper wallpaper ",$WALLPAPER"

# Uncomment below if using `swww` for smooth transitions
 swww img "$WALLPAPER" --transition-type grow --transition-duration 1

 # To use wallpaper colors(save into file) with pywal
 wal -i $WALLPAPER

killall waybar && waybar & disown || waybar & disown walogram



ROFI_THEME="$HOME/.config/rofi/config.rasi"
ESCAPED_WALLPAPER=$(printf '%s\n' "$WALLPAPER" | sed 's/[\&/]/\\&/g')



# Preload full image to warm filesystem cache
head -c 1000000 "$WALLPAPER" > /dev/null

# Define small image path
ROFI_WALLPAPER="$HOME/.cache/rofi_wallpaper_small.jpg"

# Create small resized copy for Rofi (faster to load)
convert "$WALLPAPER" -resize 800x300 "$ROFI_WALLPAPER"

# Escape the new (small) image path for sed
ESCAPED_WALLPAPER=$(printf '%s\n' "$ROFI_WALLPAPER" | sed 's/[\&/]/\\&/g')

# Path to your Rofi theme
ROFI_THEME="$HOME/.config/rofi/config.rasi"

# Replace the background-image line with the new resized path
sed -i "s|url(\".*\", width);|url(\"$ESCAPED_WALLPAPER\", width);|" "$ROFI_THEME"


#head -c 1000000 "$WALLPAPER" > /dev/null
#
#convert "$WALLPAPER" -resize 300x100 "$ROFI_WALLPAPER"
## Replace placeholder with real image path
#sed -i "s|url(\".*\", width);|url(\"$ESCAPED_WALLPAPER\", width);|" "$ROFI_THEME"



