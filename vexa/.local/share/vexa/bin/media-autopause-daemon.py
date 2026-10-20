#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PLAYERCTL = os.environ.get("PLAYERCTL", "playerctl")
STATUS_FORMAT = "{{playerInstance}}	{{status}}	{{playerName}}"
EVENT_FORMAT = "{{playerInstance}}	{{status}}	{{mpris:trackid}}	{{playerName}}"
RESTART_DELAY = 1.0
DEDUP_SECONDS = 1.5
STOP_DELAY_SECONDS = 1.5


def run_playerctl(*args):
    return subprocess.run([PLAYERCTL, *args], text=True, capture_output=True)


def get_playing_players():
    proc = run_playerctl("--all-players", "status", "--format", STATUS_FORMAT)
    if proc.returncode != 0:
        return []
    players = []
    for raw in proc.stdout.splitlines():
        if not raw.strip() or "	" not in raw:
            continue
        instance, status, name = (raw.split("	", 2) + [""])[:3]
        if status.strip() == "Playing":
            players.append({"instance": instance.strip(), "name": name.strip() or instance.strip()})
    return players


def pause_other_players(active_instance, dry_run=False):
    players = get_playing_players()
    if len(players) < 2:
        return []
    active_seen = any(p["instance"] == active_instance for p in players)
    if not active_seen:
        return []
    paused = []
    for player in players:
        instance = player["instance"]
        if instance == active_instance:
            continue
        if dry_run:
            paused.append(instance)
            continue
        proc = run_playerctl("--player", instance, "pause")
        if proc.returncode == 0:
            paused.append(instance)
    return paused


def wait_for_pause_window(active_instance):
    if STOP_DELAY_SECONDS <= 0:
        return True
    time.sleep(STOP_DELAY_SECONDS)
    players = get_playing_players()
    return any(player["instance"] == active_instance for player in players)


def monitor_forever(verbose=False):
    last_trigger = (None, None, 0.0)
    while True:
        proc = subprocess.Popen(
            [PLAYERCTL, "--all-players", "--follow", "metadata", "--format", EVENT_FORMAT],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.strip()
                if not line or "	" not in line:
                    continue
                parts = (line.split("	", 3) + ["", "", "", ""])[:4]
                instance, status, trackid, name = [p.strip() for p in parts]
                if status != "Playing" or not instance:
                    continue
                now = time.monotonic()
                if (instance, trackid) == last_trigger[:2] and (now - last_trigger[2]) < DEDUP_SECONDS:
                    continue
                if not wait_for_pause_window(instance):
                    continue
                paused = pause_other_players(instance)
                last_trigger = (instance, trackid, time.monotonic())
                if verbose and paused:
                    print(f"{instance} ({name}) started -> paused: {', '.join(paused)}", flush=True)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if verbose:
            print("playerctl follow stream exited; restarting", file=sys.stderr, flush=True)
        time.sleep(RESTART_DELAY)


def self_test():
    timeline = [
        ({"instance": "spotify.instance1", "status": "Playing", "trackid": "s1", "name": "spotify"}, [{"instance": "spotify.instance1", "name": "spotify"}]),
        ({"instance": "chromium.instance100", "status": "Playing", "trackid": "c1", "name": "chromium"}, [{"instance": "spotify.instance1", "name": "spotify"}, {"instance": "chromium.instance100", "name": "chromium"}]),
        ({"instance": "chromium.instance100", "status": "Playing", "trackid": "c1", "name": "chromium"}, [{"instance": "spotify.instance1", "name": "spotify"}, {"instance": "chromium.instance100", "name": "chromium"}]),
        ({"instance": "firefox.instance200", "status": "Playing", "trackid": "f1", "name": "firefox"}, [{"instance": "chromium.instance100", "name": "chromium"}, {"instance": "firefox.instance200", "name": "firefox"}]),
    ]
    last = (None, None, 0.0)
    for event, state in timeline:
        now = last[2] + 2.0
        duplicated = (event["instance"], event["trackid"]) == last[:2] and (now - last[2]) < DEDUP_SECONDS
        if duplicated or event["status"] != "Playing":
            paused = []
        else:
            paused = [p["instance"] for p in state if p["instance"] != event["instance"]]
            last = (event["instance"], event["trackid"], now)
        print(f"{event['instance']} -> {', '.join(paused) if paused else '(nothing to pause)'}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pause other MPRIS players when a new one starts playing.")
    parser.add_argument("--self-test", action="store_true", help="run the built-in logic demo and exit")
    parser.add_argument("--verbose", action="store_true", help="print pause actions to stdout")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(self_test())

    Path.home().joinpath('.cache').mkdir(exist_ok=True)
    monitor_forever(verbose=args.verbose)


if __name__ == "__main__":
    main()
