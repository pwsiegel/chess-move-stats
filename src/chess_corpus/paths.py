from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SAMPLE = DATA / "sample"

LUMBRA_PGN = RAW / "lumbra_otb_elite.pgn"
LUMBRA_ARCHIVE = RAW / "lumbra_otb_elite.7z"
GAMES_PARQUET_DIR = PROCESSED / "games"

SAMPLE_PGN = SAMPLE / "sample.pgn"
SAMPLE_PARQUET_DIR = SAMPLE / "games"
