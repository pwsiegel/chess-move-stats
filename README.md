# chess-move-stats

Ingest a corpus of master-level over-the-board games and run move/position
statistics on it. Source: **Lumbra's Gigabase OTB Elite** (both players
≥2400 Elo, ~900k games as of June 2026, updated monthly).

Analyses live in `notebooks/`. The Python package (`src/chess_corpus/`)
provides ingestion + a small library of streaming/parallel helpers; it's
not a CLI.

## What's here

```
src/chess_corpus/
  download.py             # Fetch Lumbra OTB Elite .7z from MEGA, extract PGN
  index_games.py          # Stream PGN → parquet shards (one row per game)
  build_sample.py         # Carve a 100-game sample for VCS
  analysis.py             # Streaming + parallel access; per-game mappers
  paths.py                # Shared filesystem paths

notebooks/
  explore_sample.ipynb        # Schema + how to read the parquet
  games_by_decade.ipynb       # DuckDB-only: counts by decade
  rook_b5.ipynb               # Marginal + conditional CDFs + top-10 PGNs

data/
  sample/                 # 100-game sample (checked in, repo is self-contained)
  raw/                    # Downloaded artifacts (gitignored, deleted by `make data`)
  processed/games/        # Full parquet index (gitignored)
```

The parquet shards preserve the full original PGN text per game, so the
indexed corpus is a complete replacement for the raw PGN — no information
is lost.

## Setup

```sh
uv sync
brew install megatools                              # for the MEGA download
uv tool install --with jupyterlab-vim jupyterlab    # once per machine
```

## Ingest the corpus

```sh
make data
```

Resolves the Lumbra wpdm URL → MEGA URL (with the `#key` from the 302
Location header, which curl auto-follow would strip), `megadl`s the 128 MB
.7z, extracts, indexes into parquet shards under `data/processed/games/`,
refreshes the sample, and deletes the raw PGN. ~5 min total.

## Run notebooks

```sh
make notebook
```

Registers the project kernel and launches JupyterLab in `notebooks/`. Each
analysis notebook has a `USE_FULL_CORPUS = False` toggle near the top —
flip it once you've run `make data`.

## Writing new analyses

Each parquet shard has columns:

| column       | type   | notes                                  |
| ------------ | ------ | -------------------------------------- |
| event/site/date/round/white/black/result/eco/opening | string | from PGN headers |
| white_elo / black_elo | int32 | null if unparseable |
| pgn          | string | full original PGN block for the game   |

Two analysis patterns:

**Header-only** — fast, pure DuckDB SQL on the parquet. See
`notebooks/games_by_decade.ipynb`.

```sql
SELECT eco, count(*) FROM 'data/processed/games/*.parquet'
GROUP BY eco ORDER BY 2 DESC;
```

**Position-level** — needs PGN replay. Add a mapper function to
`src/chess_corpus/analysis.py` (kept at module top level so `ProcessPoolExecutor`
can pickle it on macOS), then call `map_shards(your_mapper)` from a
notebook. See `notebooks/rook_b5_by_move.ipynb` for a worked example.

```python
from chess_corpus.analysis import map_shards, white_rook_to_b5
rows = map_shards(white_rook_to_b5)   # parallel across all shards
```

Single-threaded throughput is ~1,200 games/sec; with 8 cores expect ~2 min
for the full ~900k-game corpus.
