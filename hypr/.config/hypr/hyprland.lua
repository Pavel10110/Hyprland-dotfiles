-- Explicit selection via exactly one host-* Stow package, no hostname guesses.
-- Resolve relative to this entrypoint so out-of-tree verification uses staged files.
local file = debug.getinfo(1, "S").source:sub(2)
local dir = assert(file:match("^(.*)/"), "absolute config path required")
local host = dofile(dir .. "/host.lua")
assert(host == "pc" or host == "laptop", "host.lua must return pc or laptop")
dofile(dir .. "/core.lua")(host)
dofile(dir .. "/hosts/" .. host .. ".lua")
