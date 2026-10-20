#!/usr/bin/env python3
import argparse
import array
import math
import signal
import subprocess
import sys

CHARS = "▁▂▃▄▅▆▇█"
RUNNING = True
PROCESS_MS = 20
BYTES_PER_CHUNK = 640  # 20 ms at 16 kHz mono s16le
NOISE_FLOOR = 0.0025
SEGMENT_BOOST = [1.00, 1.10, 1.22, 1.10, 1.00]
IDLE_LEVELS = [0.05, 0.07, 0.10, 0.07, 0.05]
RISE_ALPHA = 0.50
FALL_ALPHA = 0.04


def _stop(*_args):
    global RUNNING
    RUNNING = False


def _segment_level(samples):
    if not samples:
        return 0.0
    peak = max(abs(x) for x in samples) / 32768.0
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768.0
    level = max(peak * 9.0, rms * 19.0)
    if level <= NOISE_FLOOR:
        return 0.0
    level = min(1.0, (level - NOISE_FLOOR) / (1.0 - NOISE_FLOOR))
    return level ** 0.36


def _glyph(level):
    idx = int(round(level * (len(CHARS) - 1)))
    idx = max(0, min(len(CHARS) - 1, idx))
    return CHARS[idx]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    proc = subprocess.Popen(
        [
            "parec",
            "--raw",
            "--format=s16le",
            "--rate=16000",
            "--channels=1",
            f"--process-time-msec={PROCESS_MS}",
            f"--latency-msec={PROCESS_MS}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    visual = IDLE_LEVELS[:]
    last_sent = None
    stream = proc.stdout
    read_chunk = getattr(stream, "read1", stream.read)

    try:
        while RUNNING:
            chunk = read_chunk(BYTES_PER_CHUNK)
            if not chunk:
                break
            if len(chunk) % 2:
                chunk = chunk[:-1]
            if len(chunk) < 10:
                continue

            samples = array.array("h")
            samples.frombytes(chunk)
            if sys.byteorder != "little":
                samples.byteswap()

            total = len(samples)
            bars = []
            for i in range(5):
                start = i * total // 5
                end = (i + 1) * total // 5
                seg = samples[start:end]
                level = _segment_level(seg)
                target = min(1.0, IDLE_LEVELS[i] + level * SEGMENT_BOOST[i])
                alpha = RISE_ALPHA if target >= visual[i] else FALL_ALPHA
                visual[i] += (target - visual[i]) * alpha
                bars.append(_glyph(visual[i]))

            payload = tuple(bars)
            if payload == last_sent:
                continue
            last_sent = payload
            subprocess.run(
                [
                    "eww",
                    "-c",
                    args.config,
                    "update",
                    f"vexa_b1={bars[0]}",
                    f"vexa_b2={bars[1]}",
                    f"vexa_b3={bars[2]}",
                    f"vexa_b4={bars[3]}",
                    f"vexa_b5={bars[4]}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()
