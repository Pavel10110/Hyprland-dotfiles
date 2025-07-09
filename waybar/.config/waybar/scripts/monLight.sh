#!/bin/bash

# Home Assistant credentials and entity
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxYzJkOWVlMWI5Y2U0Y2UxYWM4ZjQyNTkxMjcwNTE5OSIsImlhdCI6MTc0NDU3MjgyMSwiZXhwIjoyMDU5OTMyODIxfQ.kiQaHs8AZsdcyzwpv27GUYZePdOO5RkrSYFvy55VqNE"
ENTITY_ID="light.0xa4c138f95117ec15"
STATE_URL="http://192.168.0.100:8123/api/states/$ENTITY_ID"
SERVICE_URL="http://192.168.0.100:8123/api/services/light"

# Toggle
if [[ "$1" == "--toggle" ]]; then
    curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\":\"$ENTITY_ID\"}" \
        "$SERVICE_URL/toggle" > /dev/null
    sleep 0.05  # Allow HA state to update
fi

# Brightness control (scroll up/down)
if [[ "$1" == "--brightness" && "$2" != "" ]]; then
    current_brightness=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$STATE_URL" | jq '.attributes.brightness // 0')
    if [[ "$2" == "up" ]]; then
        new_brightness=$((current_brightness + 25))
    else
        new_brightness=$((current_brightness - 25))
    fi
    # Clamp between 1 and 254
    new_brightness=$(($new_brightness < 1 ? 1 : ($new_brightness > 254 ? 254 : $new_brightness)))

    curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"entity_id\":\"$ENTITY_ID\", \"brightness\":$new_brightness}" \
        "$SERVICE_URL/turn_on" > /dev/null
    sleep 0.05
fi

# Query current state and output icon
LIGHT_STATE=$(curl -s -H "Authorization: Bearer $HA_TOKEN" "$STATE_URL")
STATE=$(echo "$LIGHT_STATE" | jq -r '.state')
BRIGHTNESS=$(echo "$LIGHT_STATE" | jq -r '.attributes.brightness // empty')

if [[ "$STATE" == "on" ]]; then
    ICON="󰌵"
    BRIGHTNESS_LEVEL=$((BRIGHTNESS * 100 / 254))
    TOOLTIP="Light is ON ($BRIGHTNESS_LEVEL%)"
else
    ICON="󰌶"
    TOOLTIP="Light is OFF"
fi

echo "{\"text\": \"$ICON\", \"tooltip\": \"$TOOLTIP\"}"

