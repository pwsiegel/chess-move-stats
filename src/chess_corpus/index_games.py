"""Index a PGN corpus into parquet shards.

Streams the PGN file game-by-game, extracts standard header tags as typed
columns, and preserves the full original PGN text per row. Writes parquet
shards under data/processed/games/.

Throughput is roughly limited by disk read + regex.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from chess_corpus.paths import LUMBRA_PGN, GAMES_PARQUET_DIR

HEADER_RE = re.compile(r'^\[(\w+)\s+"((?:[^"\\]|\\.)*)"\]\s*$', re.MULTILINE)

# Columns we promote to typed parquet columns. Everything else stays in pgn text.
STRING_COLS = [
    "event",
    "site",
    "date",
    "round",
    "white",
    "black",
    "result",
    "eco",
    "opening",
]
INT_COLS = ["white_elo", "black_elo"]


def iter_game_blocks(pgn_path: Path) -> Iterator[str]:
    """Yield successive raw PGN game blocks, preserving original text."""
    buf: list[str] = []
    in_movetext = False
    with open(pgn_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("[") and in_movetext:
                yield "".join(buf)
                buf = [line]
                in_movetext = False
            else:
                buf.append(line)
                if not line.startswith("[") and line.strip():
                    in_movetext = True
        if buf and any(s.strip() for s in buf):
            yield "".join(buf)


def parse_headers(block: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in HEADER_RE.finditer(block)}


def parse_elo(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


SCHEMA = pa.schema(
    [(c, pa.string()) for c in STRING_COLS]
    + [(c, pa.int32()) for c in INT_COLS]
    + [("pgn", pa.string())]
)


def empty_batch() -> dict[str, list]:
    return {c: [] for c in STRING_COLS + INT_COLS + ["pgn"]}


def append_row(batch: dict[str, list], block: str) -> None:
    h = parse_headers(block)
    batch["event"].append(h.get("Event"))
    batch["site"].append(h.get("Site"))
    batch["date"].append(h.get("Date"))
    batch["round"].append(h.get("Round"))
    batch["white"].append(h.get("White"))
    batch["black"].append(h.get("Black"))
    batch["result"].append(h.get("Result"))
    batch["eco"].append(h.get("ECO"))
    batch["opening"].append(h.get("Opening"))
    batch["white_elo"].append(parse_elo(h.get("WhiteElo")))
    batch["black_elo"].append(parse_elo(h.get("BlackElo")))
    batch["pgn"].append(block)


def write_shard(batch: dict[str, list], shard_idx: int, out_dir: Path) -> None:
    table = pa.table(batch, schema=SCHEMA)
    out_path = out_dir / f"games-{shard_idx:05d}.parquet"
    pq.write_table(table, out_path, compression="zstd")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pgn", type=Path, default=LUMBRA_PGN)
    p.add_argument("--out", type=Path, default=GAMES_PARQUET_DIR)
    p.add_argument("--shard-size", type=int, default=200_000)
    p.add_argument("--limit", type=int, default=None, help="Stop after N games (for testing)")
    args = p.parse_args()

    if not args.pgn.exists():
        raise SystemExit(f"PGN not found: {args.pgn}. Run download.py first.")

    args.out.mkdir(parents=True, exist_ok=True)

    batch = empty_batch()
    shard_idx = 0
    n = 0
    pbar = tqdm(unit=" games")
    for block in iter_game_blocks(args.pgn):
        append_row(batch, block)
        n += 1
        pbar.update(1)
        if len(batch["pgn"]) >= args.shard_size:
            write_shard(batch, shard_idx, args.out)
            shard_idx += 1
            batch = empty_batch()
        if args.limit and n >= args.limit:
            break
    if batch["pgn"]:
        write_shard(batch, shard_idx, args.out)
    pbar.close()
    print(f"Indexed {n} games into {shard_idx + 1} shard(s) under {args.out}")


if __name__ == "__main__":
    main()
