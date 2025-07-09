return {
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = function()
      require("nvim-treesitter.configs").setup({
        -- Core settings
        auto_install = true,  -- Fixed typo (was auto_instal)
        highlight = { enable = true },
        indent = { enable = true },

        -- Add hyprlang parser
        ensure_installed = { "hyprlang" },  -- Explicitly install hyprlang

        -- Filetype recognition
        filetype_to_parsername = {
          hyprlang = { "hypr", "hyprlang" }  -- Treat these as hyprlang
        }
      })

      -- Manually set filetype for Hyprland configs
      vim.api.nvim_create_autocmd({ "BufRead", "BufNewFile" }, {
        pattern = "*/hypr/*.conf",
        callback = function()
          vim.bo.filetype = "hyprlang"  -- Force hyprlang filetype
        end
      })
    end
  }
}
