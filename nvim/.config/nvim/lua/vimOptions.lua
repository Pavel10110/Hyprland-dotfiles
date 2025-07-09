vim.cmd("set expandtab")
vim.cmd("set tabstop=4")
vim.cmd("set softtabstop=2")
vim.cmd("set shiftwidth=2")
vim.opt.number = true          -- Show absolute number on current line
vim.opt.relativenumber = true -- Show relative numbers above/below
vim.keymap.set("n", "<C-h>", "<C-w>h", { noremap = true, silent = true })
vim.keymap.set("n", "<C-l>", "<C-w>l", { noremap = true, silent = true })
vim.keymap.set("n", "<C-j>", "<C-w>j", { noremap = true, silent = true })
vim.keymap.set("n", "<C-k>", "<C-w>k", { noremap = true, silent = true })

vim.g.loaded_matchparen = 1

-- Lua (~/.config/nvim/init.lua)
vim.api.nvim_create_autocmd("BufWritePre", {
  pattern = "*",
  callback = function(ctx)
    local dir = vim.fn.fnamemodify(ctx.file, ":p:h")
    if vim.fn.isdirectory(dir) == 0 then
      vim.fn.mkdir(dir, "p")
    end
  end,
})
