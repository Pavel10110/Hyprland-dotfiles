return {
    {
        "nvim-telescope/telescope.nvim",
        -- Make ui-select a dependency so it loads with telescope
        dependencies = {
            "nvim-telescope/telescope-ui-select.nvim",
        },
        keys = {
            -- Added hidden=true to include .config and other dotfiles
            { "<leader>ff", "<cmd>Telescope find_files hidden=true<cr>", desc = "Find Files" },
            { "<leader>fg", "<cmd>Telescope live_grep<cr>", desc = "Live Grep" },
        },
        config = function()
            -- Single setup call for all of Telescope
            require("telescope").setup({
                pickers = {
                    -- Optional: You can also configure live_grep to search hidden files
                    live_grep = {
                        additional_args = function(_)
                            return { "--hidden" }
                        end
                    },
                },
                extensions = {
                    ["ui-select"] = {
                        require("telescope.themes").get_dropdown({}),
                    },
                },
            })
            
            -- Load the extension after setup
            require("telescope").load_extension("ui-select")
        end,
    },
}
