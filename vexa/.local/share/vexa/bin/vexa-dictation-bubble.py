#!/usr/bin/env python3
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

TITLE = "Vexa Dictation Bubble"
LISTEN_W, LISTEN_H = 148, 42
TEXT_W, TEXT_H = 188, 42
BAR_COUNT = 5
UPDATE_MS = 70
ACCENT = (0xCC / 255.0, 0xB3 / 255.0, 0x9B / 255.0, 0.95)


def peak_from_wav_tail(path: str | None) -> float:
    if not path or not os.path.exists(path):
        return 0.0
    try:
        size = os.path.getsize(path)
        if size <= 64:
            return 0.0
        with open(path, "rb") as fh:
            start = max(44, size - 4096)
            fh.seek(start)
            data = fh.read()
        if len(data) < 4:
            return 0.0
        usable = len(data) - (len(data) % 2)
        if usable <= 0:
            return 0.0
        samples = struct.iter_unpack("<h", data[:usable])
        peak = 0
        for (sample,) in samples:
            value = abs(sample)
            if value > peak:
                peak = value
        return min(1.0, peak / 32768.0)
    except Exception:
        return 0.0


class WaveBar(Gtk.DrawingArea):
    def __init__(self, index: int, level_getter):
        super().__init__()
        self.index = index
        self.level_getter = level_getter
        self.weight = [0.62, 0.9, 1.18, 0.9, 0.62][index % 5]
        self.set_size_request(8, 22)
        self.set_draw_func(self._draw)

    def _draw(self, area, cr, width, height, _data):
        level = self.level_getter()
        now = time.monotonic()
        wobble = 0.10 * math.sin(now * 8.0 + self.index * 0.85)
        active = max(0.0, min(1.0, level * self.weight + wobble))
        bar_h = max(4.0, min(float(height), 4.0 + active * (height - 4.0)))
        y = (height - bar_h) / 2.0
        cr.set_source_rgba(*ACCENT)
        cr.set_line_width(3.0)
        cr.set_line_cap(1)
        cr.move_to(width / 2.0, y)
        cr.line_to(width / 2.0, y + bar_h)
        cr.stroke()


class Bubble(Gtk.Application):
    def __init__(self, text: str, level_file: str | None):
        super().__init__(application_id="local.vexa.DictationBubble")
        self.text = text
        self.level_file = level_file
        self.listening = bool(level_file)
        self.current_level = 0.05
        self.window_w = LISTEN_W if self.listening else TEXT_W
        self.window_h = LISTEN_H if self.listening else TEXT_H
        self.place_attempts = 0

    def _level(self) -> float:
        return self.current_level

    def do_activate(self):
        css = b"""
        window, window.background {
          background: transparent;
          box-shadow: none;
        }
        .bubble {
          background-color: rgba(13, 13, 13, 0.68);
          border: 1px solid rgba(204, 179, 155, 0.72);
          border-radius: 18px;
          padding: 8px 12px;
        }
        .vexa-text {
          color: #e2dbd1;
          font-size: 12px;
          font-weight: 700;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.win = Gtk.ApplicationWindow(application=self, title=TITLE)
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_default_size(self.window_w, self.window_h)

        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        shell.add_css_class("bubble")
        shell.set_halign(Gtk.Align.CENTER)
        shell.set_valign(Gtk.Align.CENTER)

        if self.listening:
            wave_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            wave_box.set_halign(Gtk.Align.CENTER)
            wave_box.set_valign(Gtk.Align.CENTER)
            self.bars = []
            for idx in range(BAR_COUNT):
                bar = WaveBar(idx, self._level)
                self.bars.append(bar)
                wave_box.append(bar)
            shell.append(wave_box)
        else:
            label = Gtk.Label(label=self.text)
            label.set_xalign(0.5)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(20)
            label.add_css_class("vexa-text")
            shell.append(label)

        self.win.set_child(shell)
        self.win.present()
        GLib.timeout_add(UPDATE_MS, self._tick)
        GLib.timeout_add(120, self.place_window)

    def _tick(self):
        if self.listening:
            measured = peak_from_wav_tail(self.level_file)
            floor = 0.08 if measured <= 0.03 else 0.0
            target = max(floor, min(1.0, measured * 1.35))
            self.current_level = self.current_level * 0.65 + target * 0.35
            for bar in getattr(self, "bars", []):
                bar.queue_draw()
        return True

    def place_window(self):
        self.place_attempts += 1
        if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            return False
        try:
            clients = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True))
            match = next((c for c in clients if c.get("title") == TITLE), None)
            monitors = json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"], text=True))
            monitor = next((m for m in monitors if m.get("focused")), monitors[0] if monitors else None)
            if not match or not monitor:
                return self.place_attempts < 10
            addr = match["address"]
            scale = float(monitor.get("scale", 1) or 1)
            width = int(monitor["width"] / scale)
            height = int(monitor["height"] / scale)
            offset_x = int(monitor["x"] / scale)
            offset_y = int(monitor["y"] / scale)
            x = offset_x + (width - self.window_w) // 2
            y = offset_y + height - self.window_h - 56
            for cmd in (
                ["hyprctl", "dispatch", "setfloating", f"address:{addr}"],
                ["hyprctl", "dispatch", "resizewindowpixel", f"exact {self.window_w} {self.window_h},address:{addr}"],
                ["hyprctl", "dispatch", "movewindowpixel", f"exact {x} {y},address:{addr}"],
                ["hyprctl", "dispatch", "pin", f"address:{addr}"],
            ):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return False
        except Exception:
            return self.place_attempts < 10


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="Listening...")
    parser.add_argument("--level-file")
    args = parser.parse_args()
    Bubble(args.text, args.level_file).run([])


if __name__ == "__main__":
    main()
