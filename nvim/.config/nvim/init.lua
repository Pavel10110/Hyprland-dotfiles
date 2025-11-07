require("config.lazy")
require("vimOptions")


-- Unified clipboard setup for Hyprland/Wayland
if vim.fn.executable('wl-copy') == 1 then
  vim.g.clipboard = {
    name = 'wl-clipboard',
    copy = {
      ['+'] = 'wl-copy --foreground --type text/plain',
      ['*'] = 'wl-copy --foreground --primary --type text/plain',
    },
    paste = {
      ['+'] = 'wl-paste --no-newline',
      ['*'] = 'wl-paste --primary --no-newline',
    },
    cache_enabled = true,
  }
end

-- This makes Neovim use system clipboard for ALL operations
vim.opt.clipboard:append('unnamedplus')
