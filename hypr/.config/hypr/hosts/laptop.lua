-- thinkDed laptop profile for the shared Hyprland 0.57 Lua entrypoint.
-- Stage before the full upgrade; activate only in the coordinated new session.
hl.monitor({output="",mode="preferred",position="auto",scale=1})
hl.config({
 ["animations.enabled"]=false, ["decoration.rounding"]=4,
 ["decoration.screen_shader"]=os.getenv("HOME") .. "/.config/hypr/contrast.glsl",
 ["decoration.active_opacity"]=0.975, ["decoration.inactive_opacity"]=0.9,
 ["decoration.blur.enabled"]=false, ["decoration.shadow.enabled"]=false,
 ["misc.disable_hyprland_logo"]=true, ["misc.disable_splash_rendering"]=true,
 ["misc.animate_manual_resizes"]=false, ["misc.animate_mouse_windowdragging"]=false,
 ["general.gaps_in"]=3, ["general.gaps_out"]=5, ["general.border_size"]=1,
 ["general.resize_on_border"]=false,
})
for i = 0, 9 do
 hl.bind("SUPER + " .. i, hl.dsp.focus({workspace=tostring(i)}))
 hl.bind("SUPER + SHIFT + " .. i, hl.dsp.window.move({workspace=tostring(i),follow=true}))
end

-- Primary dictation toggle, matching the existing PC profile.
hl.bind("SUPER + V", hl.dsp.exec_cmd("~/.local/share/vexa/bin/vexa-dictate-toggle.sh"))

-- Existing laptop-only resize bindings.
hl.bind("SUPER + CTRL + h", hl.dsp.window.resize({x=-150,y=0,relative=true}))
hl.bind("SUPER + CTRL + l", hl.dsp.window.resize({x=150,y=0,relative=true}))
hl.bind("SUPER + CTRL + k", hl.dsp.window.resize({x=0,y=-100,relative=true}))
hl.bind("SUPER + CTRL + j", hl.dsp.window.resize({x=0,y=100,relative=true}))
hl.on("hyprland.start", function()
 hl.exec_cmd("python3 ~/.config/hypr/notification-start.py")
 hl.exec_cmd("Telegram", {workspace="1 silent"})
 hl.exec_cmd("zen-browser")
 hl.exec_cmd("obsidian", {workspace="7 silent"})
 hl.exec_cmd("yandexmusic")
 hl.exec_cmd("playerctld daemon & waybar & awww-daemon")
 hl.exec_cmd("hypridle")
 hl.exec_cmd("systemctl --user start hyprsunset-controller.service")
 hl.exec_cmd("wl-paste --type text --watch cliphist store")
 hl.exec_cmd("wl-paste --type image --watch cliphist store")
 hl.exec_cmd("dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE")
 hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE")
 hl.exec_cmd("systemctl --user start hyprland-session.target")
 hl.exec_cmd("gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'")
end)
