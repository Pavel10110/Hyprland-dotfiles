#!/bin/sh

if [ -z "$@" ]; then
    echo "Launch Yazi"
else
    case "$@" in
        "Launch Yazi")
            ghostty -e zsh -c "[ ! -r ~/.cache/wal/sequences ] || cat ~/.cache/wal/sequences; exec yazi" &
            ;;
    esac
fi
