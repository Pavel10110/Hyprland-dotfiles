#!/bin/sh
set -eu
# This delay runs in the worker, never in systemd-sleep or ExecStartPre.
sleep "${RGB_OFF_INITIAL_DELAY:-10}"
exec /usr/bin/env VEXA_TARGET_USER=archyper VEXA_TARGET_HOME=/home/archyper /usr/local/lib/rgb-off/rgb-off.sh
