#!/bin/bash

# Home Assistant config
HA_URL="http://192.168.0.100:8123"  # Fixed missing slash (http:/ → http://)
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxYzJkOWVlMWI5Y2U0Y2UxYWM4ZjQyNTkxMjcwNTE5OSIsImlhdCI6MTc0NDU3MjgyMSwiZXhwIjoyMDU5OTMyODIxfQ.kiQaHs8AZsdcyzwpv27GUYZePdOO5RkrSYFvy55VqNE"
ENTITY_ID="sensor.0xa4c13869f9606dd7_temperature"  # Fixed variable name (ROOM_TEMP → ENTITY_ID)

# Fetch data from HA API
fetch_data() {
    curl -s -X GET \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        "$HA_URL/api/states/$ENTITY_ID" | jq -r '.state'
}

# Output for Waybar (JSON format)
echo '{"text": "'$(fetch_data)'", "tooltip": "'$ENTITY_ID'"}'
