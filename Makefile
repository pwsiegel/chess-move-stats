# Common repo tasks. Run `make help` for a list.
#
# Requires a global JupyterLab on PATH (e.g. installed with
#     uv tool install --with jupyterlab-vim jupyterlab
# ). The project venv only supplies the kernel.
#
# `make data` also needs `megadl` from megatools:
#     brew install megatools

.DEFAULT_GOAL := help

KERNEL_NAME := chess-move-stats
KERNEL_DISPLAY := Python (chess-move-stats)

.PHONY: help notebook data sample

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

notebook: ## Register the project kernel and launch JupyterLab in notebooks/
	uv sync
	uv run python -m ipykernel install --user \
		--name $(KERNEL_NAME) \
		--display-name "$(KERNEL_DISPLAY)"
	jupyter-lab --notebook-dir=notebooks

data: ## Download Lumbra OTB Elite, index into parquet, refresh sample, drop raw PGN
	uv sync
	uv run python -m chess_corpus.download
	uv run python -m chess_corpus.index_games
	uv run python -m chess_corpus.build_sample
	rm -f data/raw/lumbra_otb_elite.pgn
	@echo "Done. Parquet shards under data/processed/games/, sample under data/sample/"

sample: ## Re-carve the 100-game sample from existing parquet shards
	uv run python -m chess_corpus.build_sample
