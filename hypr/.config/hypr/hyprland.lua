-- Explicit selection via exactly one host-* Stow package, no hostname guesses.
-- Resolve relative to this entrypoint so out-of-tree verification uses staged files.
local file = debug.getinfo(1, "S").source:sub(2)
local dir = assert(file:match("^(.*)/"), "absolute config path required")
-- Hyprland resolves the entrypoint symlink before loading it; host selection
-- remains in HOME while shared modules live beside this repository entrypoint.
local hostfile = dir .. "/host.lua"
local f = io.open(hostfile, "r")
if f then f:close() else hostfile = assert(os.getenv("HOME")) .. "/.config/hypr/host.lua" end
local host = dofile(hostfile)
assert(host == "pc" or host == "laptop", "host.lua must return pc or laptop")
dofile(dir .. "/core.lua")(host)
dofile(dir .. "/hosts/" .. host .. ".lua")
