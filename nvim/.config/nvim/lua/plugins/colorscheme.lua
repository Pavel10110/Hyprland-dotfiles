return {
  {
    "morhetz/gruvbox",
    lazy = false,
    priority = 1000,
    config = function()
      vim.o.termguicolors = true
      vim.o.background = "dark" -- optional
      vim.cmd("colorscheme gruvbox")
    end,
  },
}

