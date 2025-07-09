return {
	"nvimtools/none-ls.nvim",
	config = function()
		local null_ls = require("null-ls")
		null_ls.setup({
			sources = {
				null_ls.builtins.formatting.stylua,
				null_ls.builtins.formatting.prettier.with({
					filetypes = { "json", "jsonc", "yaml", "markdown", "html", "css", "javascript", "typescript" },
				}),
			},
		})
		vim.keymap.set("n", "<leader>gf", function()
			vim.lsp.buf.format({
				filter = function(client)
					return client.name == "null-ls"
				end,
			})
		end, {})
	end,
}
