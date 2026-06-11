#!/bin/bash
# increment_version_sudo.sh

FILE="/opt/discord/resources/build_info.json"

# Check if file exists and is readable
if ! sudo test -f "$FILE"; then
    echo "Error: File $FILE not found" >&2
    exit 1
fi

# Extract current version
current_version=$(sudo jq -r '.version' "$FILE")

# Split and increment
IFS='.' read -r major minor patch <<< "$current_version"
new_patch=$((patch + 1))
new_version="$major.$minor.$new_patch"

# Create temporary file, update, and move
temp_file=$(mktemp)
sudo jq --arg new_version "$new_version" '.version = $new_version' "$FILE" > "$temp_file"

# Move with sudo (preserves permissions)
sudo mv "$temp_file" "$FILE"

echo "Updated version: $current_version → $new_version"
