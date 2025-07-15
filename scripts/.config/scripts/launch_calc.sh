#!/bin/bash

if [[ -z "$1" ]]; then
    # If no input, show a placeholder entry
    echo "Calculator"
else
    # If input, close current Rofi and launch rofi-calc directly
    # This is the tricky part, killing rofi might not always be smooth
    pkill rofi
    rofi -show calc -modi calc &
    # You might need a small sleep here, e.g., sleep 0.1
fi

 This script is designed to be used as a Rofi script mode.
 Rofi calls script modes with the current input as the first argument ($1).
 If $1 is empty, it expects a list of selectable entries.
 If $1 is not empty, it's filtering based on user input.
 If a specific entry is selected, Rofi calls the script again with that entry's content.

ROFI_INFO_ACTION="${ROFI_INFO_ACTION:-default}" # Rofi sets ROFI_INFO_ACTION to 'default' when filtering, 'select' when an item is chosen.

