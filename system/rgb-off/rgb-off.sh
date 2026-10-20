#!/bin/bash
set -euo pipefail
PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
TARGET_USER="${VEXA_TARGET_USER:-${SUDO_USER:-}}"
TARGET_HOME="${VEXA_TARGET_HOME:-}"

if [ -z "$TARGET_USER" ] && [ "$(id -u)" -ne 0 ]; then
    TARGET_USER="$(id -un)"
fi

if [ -z "$TARGET_HOME" ] && [ -n "$TARGET_USER" ]; then
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"
fi

if [ -z "$TARGET_HOME" ] && [ "$(id -u)" -ne 0 ]; then
    TARGET_HOME="$HOME"
fi

FAST_ATTEMPTS=${RGB_OFF_ATTEMPTS:-12}
FAST_SLEEP=${RGB_OFF_SLEEP:-5}
LOG_FILE=/tmp/rgb-off-debug.$(id -u).log

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*" >> "$LOG_FILE"
}

run_openrgb() {
    if [ "$(id -u)" -eq 0 ]; then
        if [ -z "$TARGET_USER" ] || [ -z "$TARGET_HOME" ]; then
            log "missing target user/home for root OpenRGB invocation"
            return 1
        fi
        /usr/bin/runuser -u "$TARGET_USER" -- env \
            HOME="$TARGET_HOME" XDG_CONFIG_HOME="$TARGET_HOME/.config" \
            /usr/bin/openrgb "$@"
    else
        /usr/bin/openrgb "$@"
    fi
}

turn_off_device() {
    local dev="$1"
    local mode
    for mode in direct static off; do
        if run_openrgb --noautoconnect --device "$dev" --mode "$mode" --color 000000 >/dev/null 2>&1; then
            printf '%s' "$mode"
            return 0
        fi
    done
    return 1
}

write_dark_mode() {
    local bus="$1"
    /usr/bin/i2cset -y "$bus" 0x77 0xFF 0xFF >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0xFF 0xFF >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x01 0x04 >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x00 0x00 >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x03 0x00 >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x00 0x00 >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x03 0xAA >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x00 0x00 >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x03 0xFA >/dev/null
    /usr/bin/i2cset -y "$bus" 0x77 0x00 0x00 >/dev/null
}

build_bus_list() {
    local -a discovered=()
    local dev bus
    for dev in /dev/i2c-*; do
        [ -e "$dev" ] || continue
        bus=${dev##*-}
        discovered+=("$bus")
    done

    local -a ordered=()
    local candidate
    for candidate in 5 0 "${discovered[@]}"; do
        [ -n "$candidate" ] || continue
        case " ${ordered[*]} " in
            *" $candidate "*) ;;
            *) ordered+=("$candidate") ;;
        esac
    done
    printf '%s\n' "${ordered[@]}"
}

turn_off_ram_once() {
    local bus
    while IFS= read -r bus; do
        [ -n "$bus" ] || continue
        if write_dark_mode "$bus" 2>/dev/null; then
            printf '%s' "$bus"
            return 0
        fi
    done < <(build_bus_list)
    return 1
}

main() {
    local attempt gpu_state board_state ram_state ram_bus

    for attempt in $(seq 1 "$FAST_ATTEMPTS"); do
        gpu_state=fail
        board_state=fail
        ram_state=fail
        ram_bus=

        if gpu_state=$(turn_off_device 'Gigabyte GeForce RTX 3060 Gaming OC V2'); then :; else gpu_state=fail; fi
        if board_state=$(turn_off_device 'ASRock B560 Steel Legend'); then :; else board_state=fail; fi
        if ram_bus=$(turn_off_ram_once); then ram_state="bus-$ram_bus"; else ram_state=fail; fi

        log "attempt $attempt/$FAST_ATTEMPTS user=$(id -un) gpu=$gpu_state board=$board_state ram=$ram_state"

        if [ "$gpu_state" != fail ] && [ "$board_state" != fail ] && [ "$ram_state" != fail ]; then
            return 0
        fi

        if [ "$attempt" -lt "$FAST_ATTEMPTS" ]; then
            sleep "$FAST_SLEEP"
        fi
    done

    return 1
}

main
