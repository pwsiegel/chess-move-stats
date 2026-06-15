"""Carve a small sample from the indexed parquet shards for VCS.

Reads the first N rows from data/processed/games/ and writes both:

  - data/sample/sample.pgn          (concatenated raw PGN blocks)
  - data/sample/games/games-00000.parquet  (parquet with the same schema)

These get checked in so the repo is self-contained — anyone cloning the
project can run the queries and open the notebook against the sample
without having to download the full Lumbra archive first.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow.parquet as pq

from chess_corpus.paths import GAMES_PARQUET_DIR, SAMPLE, SAMPLE_PARQUET_DIR, SAMPLE_PGN


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=100, help="Number of games to keep")
    p.add_argument("--source", type=Path, default=GAMES_PARQUET_DIR)
    args = p.parse_args()

    shards = sorted(args.source.glob("*.parquet"))
    if not shards:
        raise SystemExit(f"No shards under {args.source}. Run `make data` first.")

    table = pq.read_table(shards[0])
    take = min(args.n, table.num_rows)
    sample = table.slice(0, take)

    SAMPLE.mkdir(parents=True, exist_ok=True)
    SAMPLE_PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    pq.write_table(
        sample, SAMPLE_PARQUET_DIR / "games-00000.parquet", compression="zstd"
    )

    with open(SAMPLE_PGN, "w", encoding="utf-8") as fh:
        for pgn_text in sample.column("pgn").to_pylist():
            fh.write(pgn_text)
            if not pgn_text.endswith("\n\n"):
                fh.write("\n" if pgn_text.endswith("\n") else "\n\n")

    print(f"Wrote {take} games to:")
    print(f"  {SAMPLE_PGN}")
    print(f"  {SAMPLE_PARQUET_DIR}/games-00000.parquet")


if __name__ == "__main__":
    main()
