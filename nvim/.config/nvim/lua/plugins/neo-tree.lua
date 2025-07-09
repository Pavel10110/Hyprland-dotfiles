return {
	{
		"nvim-neo-tree/neo-tree.nvim",
		branch = "v3.x",
		keys = { { "<leader>n", "<cmd>Neotree toggle<cr>", desc = "opens a neotree" } },
		opts = {
			filesystem = {

				window = {
					mappings = {
						["l"] = "set_root",
						["h"] = "navigate_up",
						["."] = "toggle_hidden",
					},
				},
			},
		},
		dependencies = {
			"nvim-lua/plenary.nvim",
			"nvim-tree/nvim-web-devicons", -- not strictly required, but recommended
			"MunifTanjim/nui.nvim",
			{ "3rd/image.nvim", opts = {} }, -- Optional image support in preview window: See `# Preview Mode` for more information
		},
		lazy = false, -- neo-tree will lazily load itself
		---@module "neo-tree"
		---@type neotree.Config?
	},
}
