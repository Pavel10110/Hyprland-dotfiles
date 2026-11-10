return {
  {
    "mason-org/mason.nvim",
    opts = {},
  },
  {
    "mason-org/mason-lspconfig.nvim",
    opts = {
      ensure_installed = { "lua_ls" },
    },
  },
  {
    "neovim/nvim-lspconfig",
    config = function()
      local capabilities = require("cmp_nvim_lsp").default_capabilities()

      -- Let nvim-lspconfig supply cmd, root markers and Lua filetypes.
      -- Both hosts run Neovim 0.12; do not start a cmd-less client in every buffer.
      vim.lsp.config("lua_ls", {
        capabilities = capabilities,
        settings = {
          Lua = {
            diagnostics = {
              globals = { "vim" }
            },
            workspace = {
              checkThirdParty = false,
            },
            telemetry = { enable = false },
          }
        }
      })
      vim.lsp.enable("lua_ls")

      vim.keymap.set("n", "gd", vim.lsp.buf.definition)
      vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action)

      vim.diagnostic.config({
        virtual_text = {
          prefix = ">>",
          spacing = 4,
          source = "if_many",
        },
        signs = true,
        underline = true,
        update_in_insert = false,
        severity_sort = true,
      })
    end,
  },
}
--return {
--  {
--    "mason-org/mason.nvim",
--    opts = {},
--  },
--  {
--    "mason-org/mason-lspconfig.nvim",
--    opts = {
--      ensure_installed = { "lua_ls" },
--    },
--  },
--  {
--    "neovim/nvim-lspconfig",
--    config = function()
--      local capabilities = require("cmp_nvim_lsp").default_capabilities()
--
--      local lspconfig = require("lspconfig")
--      lspconfig.lua_ls.setup({
--        capabilities = capabilities,
--      })
--      vim.keymap.set("n", "gd", vim.lsp.buf.definition)
--      vim.keymap.set("n", "<leader>ca", vim.lsp.buf.code_action)
--
--      vim.diagnostic.config({
--        virtual_text = {
--          prefix = ">>", -- or '', '>>', '■', etc.
--          spacing = 4,
--          source = "if_many",
--        },
--        signs = true,
--        underline = true,
--        update_in_insert = false,
--        severity_sort = true,
--      })
--    end,
--  },
--}
