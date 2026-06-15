"""How often is <piece> on <square> across master-level positions?

Streams parquet shards, filters by minimum Elo, replays each game with
python-chess, and counts positions where the requested piece sits on the
requested square. Reports both:

  - position-frequency:   matching positions / total positions
  - game-frequency:       games where it occurs at least once / games scanned

Examples
--------
    uv run python -m chess_corpus.queries.piece_on_square --piece R --square b5
    uv run python -m chess_corpus.queries.piece_on_square --piece r --square b5 --min-elo 2400
    uv run python -m chess_corpus.queries.piece_on_square --piece R --square b5 --either-color
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import chess
import chess.pgn
import pyarrow.parquet as pq
from tqdm import tqdm

from chess_corpus.paths import GAMES_PARQUET_DIR

PIECE_MAP = {
    "P": chess.Piece(chess.PAWN, chess.WHITE),
    "N": chess.Piece(chess.KNIGHT, chess.WHITE),
    "B": chess.Piece(chess.BISHOP, chess.WHITE),
    "R": chess.Piece(chess.ROOK, chess.WHITE),
    "Q": chess.Piece(chess.QUEEN, chess.WHITE),
    "K": chess.Piece(chess.KING, chess.WHITE),
    "p": chess.Piece(chess.PAWN, chess.BLACK),
    "n": chess.Piece(chess.KNIGHT, chess.BLACK),
    "b": chess.Piece(chess.BISHOP, chess.BLACK),
    "r": chess.Piece(chess.ROOK, chess.BLACK),
    "q": chess.Piece(chess.QUEEN, chess.BLACK),
    "k": chess.Piece(chess.KING, chess.BLACK),
}


def scan(
    shard_dir: Path,
    piece_char: str,
    square_name: str,
    min_elo: int | None,
    either_color: bool,
    limit: int | None,
) -> None:
    target_square = chess.parse_square(square_name)
    target_piece = PIECE_MAP[piece_char]
    if either_color:
        target_piece_type = target_piece.piece_type
    else:
        target_piece_type = None

    shards = sorted(shard_dir.glob("*.parquet"))
    if not shards:
        raise SystemExit(f"No parquet shards under {shard_dir}. Run index_games.py first.")

    games_scanned = 0
    games_matched = 0
    positions_scanned = 0
    positions_matched = 0

    pbar = tqdm(unit=" games")
    for shard_path in shards:
        cols = ["pgn", "white_elo", "black_elo"]
        table = pq.read_table(shard_path, columns=cols)
        pgn_col = table.column("pgn")
        w_col = table.column("white_elo")
        b_col = table.column("black_elo")
        for i in range(table.num_rows):
            if min_elo is not None:
                w = w_col[i].as_py()
                b = b_col[i].as_py()
                if w is None or b is None or w < min_elo or b < min_elo:
                    continue
            pgn_text = pgn_col[i].as_py()
            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if game is None:
                continue
            board = game.board()
            matched_in_game = False
            n_pos = 1  # initial position
            piece = board.piece_at(target_square)
            if piece is not None and (
                (target_piece_type is not None and piece.piece_type == target_piece_type)
                or (target_piece_type is None and piece == target_piece)
            ):
                positions_matched += 1
                matched_in_game = True
            for move in game.mainline_moves():
                board.push(move)
                n_pos += 1
                piece = board.piece_at(target_square)
                if piece is None:
                    continue
                if target_piece_type is not None:
                    if piece.piece_type == target_piece_type:
                        positions_matched += 1
                        matched_in_game = True
                else:
                    if piece == target_piece:
                        positions_matched += 1
                        matched_in_game = True
            positions_scanned += n_pos
            games_scanned += 1
            if matched_in_game:
                games_matched += 1
            pbar.update(1)
            if limit and games_scanned >= limit:
                pbar.close()
                report(
                    piece_char,
                    square_name,
                    either_color,
                    games_scanned,
                    games_matched,
                    positions_scanned,
                    positions_matched,
                )
                return
    pbar.close()
    report(
        piece_char,
        square_name,
        either_color,
        games_scanned,
        games_matched,
        positions_scanned,
        positions_matched,
    )


def report(
    piece_char: str,
    square: str,
    either_color: bool,
    games_scanned: int,
    games_matched: int,
    positions_scanned: int,
    positions_matched: int,
) -> None:
    label = f"{'either-color ' if either_color else ''}{piece_char} on {square}"
    print(f"\nQuery: {label}")
    print(f"  games scanned:      {games_scanned:>12,}")
    print(f"  games with match:   {games_matched:>12,}", end="")
    if games_scanned:
        print(f"   ({100 * games_matched / games_scanned:.2f}%)")
    else:
        print()
    print(f"  positions scanned:  {positions_scanned:>12,}")
    print(f"  positions matched:  {positions_matched:>12,}", end="")
    if positions_scanned:
        print(f"   ({100 * positions_matched / positions_scanned:.4f}%)")
    else:
        print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--piece",
        required=True,
        help="Piece letter: PNBRQK (white) or pnbrqk (black). Use --either-color to ignore color.",
    )
    p.add_argument("--square", required=True, help="Square name, e.g. b5")
    p.add_argument("--min-elo", type=int, default=None, help="Both players must be >= this Elo")
    p.add_argument(
        "--either-color",
        action="store_true",
        help="Match the piece type regardless of color (uses --piece only for type)",
    )
    p.add_argument("--shard-dir", type=Path, default=GAMES_PARQUET_DIR)
    p.add_argument("--limit", type=int, default=None, help="Stop after N games (for testing)")
    args = p.parse_args()

    if args.piece not in PIECE_MAP:
        raise SystemExit(f"--piece must be one of {''.join(PIECE_MAP)}")

    scan(
        args.shard_dir,
        args.piece,
        args.square,
        args.min_elo,
        args.either_color,
        args.limit,
    )


if __name__ == "__main__":
    main()
