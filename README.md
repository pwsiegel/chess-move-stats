# chess-move-stats

Ingest a corpus of master-level over-the-board games and run move/position
statistics on it. Source: **Lumbra's Gigabase OTB Elite** (both players
≥2400 Elo, ~900k games as of June 2026, updated monthly).

## What's here

```
src/chess_corpus/
  download.py             # Fetch Lumbra OTB Elite .7z from MEGA, extract PGN
  index_games.py          # Stream PGN → parquet shards (one row per game)
  build_sample.py         # Carve a 100-game sample for VCS
  paths.py                # Shared filesystem paths
  queries/
    piece_on_square.py    # Example: how often is <piece> on <square>?

data/
  sample/                 # 100-game sample (checked in, repo is self-contained)
    sample.pgn
    games/games-00000.parquet
  raw/                    # Downloaded artifacts (gitignored, deleted by `make data`)
  processed/games/        # Full parquet index (gitignored)
```

The parquet shards preserve the full original PGN text per game, so the
indexed corpus is a complete replacement for the raw PGN — no information
is lost.

## Setup

```sh
uv sync
brew install megatools    # for downloading the MEGA-hosted archive
```

### Notebooks

This project uses a global JupyterLab (installed once per machine) with
project-specific kernels. To set up JupyterLab the first time:

```sh
uv tool install --with jupyterlab-vim jupyterlab    # adjust extensions to taste
```

Then from the project root:

```sh
make notebook
```

which registers a `chess-move-stats` kernel pointing at this venv and
launches JupyterLab in `notebooks/`.

## Ingest the full corpus

```sh
make data
```

This:

1. Resolves the Lumbra wpdm URL → MEGA URL (with decryption key from the
   302 Location header, which curl auto-follow would strip)
2. `megadl`s the ~128 MB .7z
3. Extracts the PGN
4. Streams it into parquet shards under `data/processed/games/`
5. Deletes the raw PGN (the parquet preserves it)

Expect ~5 min total (most of it the MEGA download; indexing 900k games is ~15 sec).

## Try a query

The example query answers the original motivating question:

```sh
# How often is a white rook on b5? (no Elo filter needed — Lumbra Elite is already 2400+)
uv run python -m chess_corpus.queries.piece_on_square --piece R --square b5

# Either-color rook on b5
uv run python -m chess_corpus.queries.piece_on_square --piece R --square b5 --either-color
```

Reports both:

- **position frequency**: matching positions / total positions
- **game frequency**: games where it occurs at least once / games scanned

Piece letters: `PNBRQK` (white) / `pnbrqk` (black). Add `--either-color` to
match by piece type regardless of color.

To try a query without the full download, point at the committed sample:

```sh
uv run python -m chess_corpus.queries.piece_on_square \
    --piece R --square b5 --shard-dir data/sample/games
```

## Adding new queries

Each parquet shard has columns:

| column       | type   | notes                                  |
| ------------ | ------ | -------------------------------------- |
| event/site/date/round/white/black/result/eco/opening | string | from PGN headers |
| white_elo / black_elo | int32 | null if unparseable |
| pgn          | string | full original PGN block for the game   |

A new query is: load shards with pyarrow or duckdb, filter on the typed
columns, then replay `pgn` with `python-chess`. See `queries/piece_on_square.py`
as a template.

DuckDB can read the parquet shards directly:

```sql
SELECT eco, count(*) FROM 'data/processed/games/*.parquet'
GROUP BY eco ORDER BY 2 DESC;
```
