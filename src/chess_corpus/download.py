"""Download Lumbra's Gigabase OTB Elite (≥2400 Elo) and extract its PGN.

The Lumbra download page links to a MEGA-hosted 7z. MEGA links require a
JS-decrypted key fragment that curl/requests can't follow directly, but the
wpdm endpoint's 302 redirect Location header preserves the full URL with
key. We grab it from there and hand it to `megadl`.

Modes
-----
  (default)         resolve Lumbra wpdm URL → MEGA → megadl
  --archive <path>  use an already-downloaded .7z (skips network)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import py7zr
import requests

from chess_corpus.paths import LUMBRA_ARCHIVE, LUMBRA_PGN, RAW

# OTB Elite (Elo > 2400) on Lumbra. The slug "otb-2020-2024-2" is a relic —
# the description confirms it's all-time games with both players ≥2400.
LUMBRA_WPDM_URL = "https://lumbrasgigabase.com/download/otb-2020-2024-2/?wpdmdl=9964"


def resolve_mega_url(wpdm_url: str) -> str:
    """Hit the wpdm endpoint without following redirects so we keep the
    Location header (and its `#<key>` fragment, which curl auto-follow strips).
    """
    r = requests.head(
        wpdm_url, allow_redirects=False, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
    )
    if r.status_code != 302 or "location" not in r.headers:
        raise SystemExit(
            f"Expected 302 redirect from {wpdm_url}, got {r.status_code}.\n"
            "Lumbra may have changed its download flow — inspect the page manually."
        )
    location = r.headers["location"]
    if "mega.nz" not in location:
        raise SystemExit(f"Unexpected redirect target: {location}")
    return location


def megadl(mega_url: str, dest_dir: Path) -> Path:
    if shutil.which("megadl") is None:
        raise SystemExit(
            "megadl not found on PATH. Install with: brew install megatools"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    before = set(dest_dir.iterdir())
    cmd = ["megadl", "--path", str(dest_dir), mega_url]
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=True)
    after = set(dest_dir.iterdir())
    new_files = after - before
    if not new_files:
        raise SystemExit("megadl reported success but no new files appeared.")
    if len(new_files) > 1:
        raise SystemExit(f"megadl produced multiple files: {new_files}")
    return new_files.pop()


def extract_pgn(archive_path: Path, out_pgn: Path) -> None:
    out_pgn.parent.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive_path, "r") as z:
        names = z.getnames()
        pgn_names = [n for n in names if n.lower().endswith(".pgn")]
        if not pgn_names:
            raise SystemExit(f"No .pgn entries in {archive_path}: {names}")
        # Extract straight to disk under a scratch dir, then concat into out_pgn.
        scratch = out_pgn.parent / "_extract_scratch"
        scratch.mkdir(exist_ok=True)
        z.extract(path=scratch, targets=pgn_names)
        with open(out_pgn, "wb") as out:
            for name in pgn_names:
                src = scratch / name
                with open(src, "rb") as fh:
                    shutil.copyfileobj(fh, out, length=1 << 20)
                src.unlink()
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"Wrote {out_pgn} ({out_pgn.stat().st_size / 1e9:.2f} GB)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--archive",
        type=Path,
        help="Path to an already-downloaded .7z (skips the network fetch)",
    )
    p.add_argument(
        "--keep-archive",
        action="store_true",
        help="Don't delete the .7z after extracting (default: delete)",
    )
    p.add_argument("--out", type=Path, default=LUMBRA_PGN)
    args = p.parse_args()

    if args.archive:
        archive_path = args.archive
    else:
        mega_url = resolve_mega_url(LUMBRA_WPDM_URL)
        print(f"Resolved MEGA URL with key", file=sys.stderr)
        archive_path = megadl(mega_url, RAW)
        # Standardize the name so downstream paths are predictable.
        if archive_path != LUMBRA_ARCHIVE:
            archive_path = archive_path.rename(LUMBRA_ARCHIVE)

    extract_pgn(archive_path, args.out)

    if not args.keep_archive and not args.archive:
        archive_path.unlink(missing_ok=True)
        print(f"Removed {archive_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
