#!/bin/sh

if [ -z "$@" ]; then
    echo "Launch Yazi"
else
    case "$@" in
        "Launch Yazi")
            ghostty -e zsh -c "cat ~/.cache/wal/sequences && yazi" &
            ;;
    esac
fi
