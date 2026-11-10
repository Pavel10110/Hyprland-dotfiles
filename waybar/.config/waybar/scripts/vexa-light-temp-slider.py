#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import os
import json
from ha_runtime import load_env, request
import threading
import time
import sys

# --- Configuration ---
# Launcher validates private.env and passes these in the child environment only.
# All HTTP uses the same private loader/request implementation as status helpers.
HA_TOKEN = os.getenv("HA_TOKEN") # Home Assistant Long-Lived Access Token
ENTITY_ID = os.getenv("HA_ENTITY_ID") # Your light entity ID
HA_BASE_URL = os.getenv("HA_URL") # Your Home Assistant URL (e.g., http://192.168.0.100:8123)

# Construct full URLs
STATE_URL = f"{HA_BASE_URL}/api/states/{ENTITY_ID}"
SERVICE_URL = f"{HA_BASE_URL}/api/services/light/turn_on"

# Constants for color temperature in Kelvin (adjust based on your light's capabilities)
MIN_KELVIN = 2000
MAX_KELVIN = 6500

# --- CSS for window and widget styling ---
CSS_STYLE = """
/* Target the main window by its Gtk.Window name property */
window.LightTempSliderWindow {
    background-color: green;
    border-radius: 30px;
}

/* Style the Gtk.Scale widget itself */
scale {
    background-color: transparent;
    border-radius: 30px;
}

/* Style the 'trough' (the track) of the slider */
scale trough {
    min-height: 5px;
    background-image: linear-gradient(to right, #ffbe0b, #59b1f7);
    border-radius: 30px;
}

/* Style the 'highlight' (the filled part of the track) */
scale highlight {
    border-radius: 30px;
    background-color: transparent;
}

/* Style the 'slider' (the handle/grip) */
scale slider {
    border-radius: 30px;
    min-width: 30px;
    min-height: 25px;
}

/* Optional: Style the slider value text */
scale value {
    color: #e0e0e0;
    font-weight: bold;
}
"""

class LightTempSlider(Gtk.Window):
    def __init__(self, pos_x=None, pos_y=None):
        Gtk.Window.__init__(self, title="Light Temperature")
        self.set_default_size(300, 50)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_name("LightTempSliderWindow") # Crucial for CSS styling

        # This sets the WM_CLASS for the window.
        # DeprecationWarning is okay, it still works.
        self.set_wmclass("light_temp_slider", "LightTempSlider")

        # Apply CSS for styling and transparency
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS_STYLE.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.set_app_paintable(True)

        # Check for compositor support
        screen = self.get_screen()
        if not screen.is_composited():
            print("Warning: Compositor not detected. Window transparency might not work as expected.")

        self.connect("destroy", Gtk.main_quit)
        self.connect("show", self.on_show)

        self.timeout_id = None
        self.focus_out_disconnect_id = None

        # Delay connecting the focus-out event
        # Changed from 150 to 500 (0.5 seconds) to prevent immediate disappearance
        GLib.timeout_add(1000, self.connect_focus_out_delayed)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Create the slider (Gtk.Scale)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, MIN_KELVIN, MAX_KELVIN, 1)
        self.scale.set_digits(0)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale.set_hexpand(True)
        self.scale.connect("value-changed", self.on_scale_changed)
        self.scale.connect("button-release-event", self.on_scale_released)
        vbox.pack_start(self.scale, True, True, 0)

        # Store position for later use in on_show.
        # However, due to Hyprland issues, self.move() in on_show is currently commented out.
        # These values will be received but not used for direct positioning by GTK itself.
        self.target_pos_x = pos_x
        self.target_pos_y = pos_y

        # Fetch the initial light state
        self.fetch_initial_state()

    def connect_focus_out_delayed(self):
        """Connects the focus-out event after a short delay."""
        if self.get_window() is not None:
            self.focus_out_disconnect_id = self.connect("focus-out-event", self.on_focus_out)
        return False # Return False to ensure this timeout runs only once

    def on_show(self, widget):
        """Called when the window is first shown (mapped). Responsible for starting auto-close timer."""
        # Due to your Hyprland's 'Invalid dispatcher' issue, GTK's self.move() is being
        # ignored or overridden. We leave it commented out for the window to appear.
        # #if self.target_pos_x is not None and self.target_pos_y is not None:
        # #    self.move(self.target_pos_x, self.target_pos_y)
        self.reset_timeout()

    def fetch_initial_state(self):
        """Fetches the current light state (especially kelvin) from Home Assistant."""
        def _fetch():
            if not all([HA_TOKEN, ENTITY_ID, HA_BASE_URL]):
                print("Error: Home Assistant credentials/entity not fully configured.")
                GLib.idle_add(self.destroy)
                return

            try:
                data = request(load_env(), 'states/' + ENTITY_ID)

                current_kelvin = data.get('attributes', {}).get('color_temp_kelvin')
                if current_kelvin is not None:
                    GLib.idle_add(self.set_slider_value, current_kelvin)
                else:
                    print(f"Color temperature (kelvin) attribute not found for {ENTITY_ID}.")

            except Exception as e:
                print('Home Assistant state unavailable.')
                GLib.idle_add(self.destroy)

        threading.Thread(target=_fetch).start()

    def set_slider_value(self, value):
        """Sets the slider's current value."""
        clamped_value = max(MIN_KELVIN, min(MAX_KELVIN, value))
        self.scale.set_value(clamped_value)

    def on_scale_changed(self, scale):
        """Called when the slider's value changes (e.g., dragging)."""
        pass

    def on_scale_released(self, scale, event):
        """Called when the mouse button is released after dragging the slider."""
        new_kelvin = int(scale.get_value())
        self.update_light_temperature(new_kelvin)
        self.reset_timeout()

    def update_light_temperature(self, kelvin):
        """Sends the new Kelvin value to Home Assistant."""
        def _update():
            if not all([HA_TOKEN, ENTITY_ID, HA_BASE_URL]):
                print("Error: Home Assistant credentials/entity not fully configured for update.")
                return

            try:
                request(load_env(), 'services/light/turn_on',
                        {'entity_id': ENTITY_ID, 'kelvin': kelvin})
            except Exception:
                print('Home Assistant temperature update unavailable.')

        threading.Thread(target=_update).start()

    def on_focus_out(self, widget, event):
        """Called when the window loses focus (e.g., user clicks outside)."""
        # Check if the underlying GdkWindow still exists before attempting to destroy.
        # If get_window() returns None, the window is already being destroyed or destroyed.
        if self.get_window() is not None:
            self.destroy()

    def reset_timeout(self):
        """Resets or starts the auto-close timer."""
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
        self.timeout_id = GLib.timeout_add_seconds(10, self.on_timeout)

    def on_timeout(self):
        """Called when the auto-close timeout expires."""
        self.destroy()
        return False

def main():
    pos_x = None
    pos_y = None
    # Parse command line arguments for position.
    # These are passed by the shell script, but the GTK window won't
    # use them for positioning directly due to Hyprland's behavior.
    if "--pos-x" in sys.argv:
        try:
            pos_x = int(sys.argv[sys.argv.index("--pos-x") + 1])
        except (ValueError, IndexError):
            pass
    if "--pos-y" in sys.argv:
        try:
            pos_y = int(sys.argv[sys.argv.index("--pos-y") + 1])
        except (ValueError, IndexError):
            pass

    win = LightTempSlider(pos_x, pos_y)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
