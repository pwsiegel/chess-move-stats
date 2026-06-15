"""Re-shard existing parquet shards into a different shard size.

Avoids re-downloading the corpus when you change `--shard-size`. Reads all
existing shards under `data/processed/games/` into one table, then writes
new shards under the same path.

Usage
-----
    uv run python -m chess_corpus.reshard --shard-size 60000
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow.parquet as pq

from chess_corpus.paths import GAMES_PARQUET_DIR


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shard-size", type=int, default=60_000)
    p.add_argument("--shard-dir", type=Path, default=GAMES_PARQUET_DIR)
    args = p.parse_args()

    shards = sorted(args.shard_dir.glob("*.parquet"))
    if not shards:
        raise SystemExit(f"No shards under {args.shard_dir}")

    print(f"Reading {len(shards)} existing shard(s) ...")
    table = pq.read_table(args.shard_dir)
    print(f"  total rows: {table.num_rows:,}")

    # Wipe old shards before writing new ones (would otherwise mix sizes).
    for old in shards:
        old.unlink()

    n_new = 0
    for start in range(0, table.num_rows, args.shard_size):
        end = min(start + args.shard_size, table.num_rows)
        slice_ = table.slice(start, end - start)
        out = args.shard_dir / f"games-{n_new:05d}.parquet"
        pq.write_table(slice_, out, compression="zstd")
        n_new += 1
    print(f"Wrote {n_new} new shard(s) of up to {args.shard_size} games each.")


if __name__ == "__main__":
    main()
