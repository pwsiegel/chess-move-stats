"""Streaming + parallel access to the indexed corpus.

Notebooks import from here to avoid repeating the parquet-load + PGN-parse
boilerplate. Two main entry points:

  - per_shard_iter(shard, mapper)      single-process, streams one shard
  - map_shards(mapper, reducer, ...)   ProcessPoolExecutor across all shards

`mapper` takes (headers_dict, chess.pgn.Game) and returns anything pickleable
(typically a dict, list of dicts, or partial aggregate).

`reducer` takes a list of per-shard results and combines them. Default
reducer just flattens lists.
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

import chess
import chess.pgn
import pyarrow.parquet as pq
from tqdm.auto import tqdm

from chess_corpus.paths import GAMES_PARQUET_DIR

T = TypeVar("T")

# Standard piece values for material counts (kings excluded — always on board).
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


def total_material(board: chess.Board) -> int:
    return sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values())


def iter_shard(shard_path: Path) -> Iterator[tuple[dict[str, Any], chess.pgn.Game]]:
    """Yield (headers, parsed game) from a single parquet shard."""
    table = pq.read_table(shard_path)
    col_names = table.column_names
    cols = {c: table.column(c).to_pylist() for c in col_names}
    n = table.num_rows
    for i in range(n):
        headers = {c: cols[c][i] for c in col_names if c != "pgn"}
        game = chess.pgn.read_game(io.StringIO(cols["pgn"][i]))
        if game is None:
            continue
        yield headers, game


def per_shard_iter(
    shard_path: Path,
    mapper: Callable[[dict[str, Any], chess.pgn.Game], T],
) -> list[T]:
    """Apply mapper to every game in a shard. Returns a list of results."""
    return [mapper(h, g) for h, g in iter_shard(shard_path)]


def _shard_worker(args: tuple[Path, Callable]) -> Any:
    shard_path, mapper = args
    return per_shard_iter(shard_path, mapper)


def map_shards(
    mapper: Callable[[dict[str, Any], chess.pgn.Game], T],
    shard_dir: Path = GAMES_PARQUET_DIR,
    reducer: Callable[[list[list[T]]], Any] | None = None,
    max_workers: int | None = None,
    progress: bool = True,
) -> Any:
    """Run mapper over every game across all shards in parallel.

    Returns reducer(per_shard_results). Default reducer concatenates the
    per-shard lists into one flat list. Per-shard results are preserved in
    input (sorted) order regardless of completion order.
    """
    shards = sorted(shard_dir.glob("*.parquet"))
    if not shards:
        raise RuntimeError(f"No shards under {shard_dir}")
    if max_workers is None:
        max_workers = max(1, (os.cpu_count() or 2) - 1)
    if reducer is None:
        reducer = lambda per_shard: [x for sub in per_shard for x in sub]

    results: list[Any] = [None] * len(shards)
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_shard_worker, (s, mapper)): i for i, s in enumerate(shards)
        }
        pbar = tqdm(total=len(shards), desc="shards", disable=not progress)
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
            pbar.update(1)
        pbar.close()
    return reducer(results)


# ---------------------------------------------------------------------------
# Mappers for specific analyses. Each takes (headers, game) and returns one
# row of summary stats. Keep them at module top-level so ProcessPoolExecutor
# can pickle them on macOS (spawn start method).
# ---------------------------------------------------------------------------


def white_rook_to_b5(headers: dict, game: chess.pgn.Game) -> dict:
    """Summarize white's rook-to-b5 history in a single game.

    Returns
    -------
    first_rb5_fullmove : int | None
        The full move number on which white first played a rook to b5
        (None if never).
    min_material_at_rb5 : int | None
        The lowest total material (both sides, kings excluded) at any
        white-rook-to-b5 position. None if never. Material decreases
        monotonically through a game, so this is the material *just after*
        the latest white Rb5.
    n_white_moves : int
        How many white moves the game contained — used to know whether the
        game even had a chance to reach a given move number N.
    """
    board = game.board()
    first_fullmove: int | None = None
    min_material: int | None = None
    n_white_moves = 0

    for move in game.mainline_moves():
        if board.turn == chess.WHITE:
            n_white_moves += 1
            piece = board.piece_at(move.from_square)
            is_white_rb5 = (
                piece is not None
                and piece.piece_type == chess.ROOK
                and move.to_square == chess.B5
            )
            this_fullmove = board.fullmove_number
        else:
            is_white_rb5 = False
            this_fullmove = None

        board.push(move)

        if is_white_rb5:
            mat = total_material(board)
            if first_fullmove is None:
                first_fullmove = this_fullmove
            if min_material is None or mat < min_material:
                min_material = mat

    return {
        "first_rb5_fullmove": first_fullmove,
        "min_material_at_rb5": min_material,
        "n_white_moves": n_white_moves,
    }

