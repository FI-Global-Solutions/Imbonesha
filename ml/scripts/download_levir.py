"""Download the LEVIR-CD change detection dataset.

LEVIR-CD is a public building change detection dataset with 637 pairs of
1024×1024 pixel Google Earth images covering multiple cities in Texas.

Primary source (if accessible):
    https://justchenhao.github.io/LEVIR/

Hugging Face mirror (more reliable):
    https://huggingface.co/datasets/satellogic/levir-cd

The dataset is ~600 MB compressed; ~1.2 GB unpacked.  Do NOT commit it —
ml/data/ is in .gitignore.

Usage:
    python ml/scripts/download_levir.py [--dest ml/data/LEVIR-CD]

After download the directory structure will be:
    ml/data/LEVIR-CD/
        train/A/   — baseline images
        train/B/   — current images
        train/label/  — change masks (255=changed)
        test/A/
        test/B/
        test/label/
        val/...
"""

from __future__ import annotations

import argparse
import logging
import os
import zipfile
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DEST = Path(__file__).resolve().parents[1] / "data" / "LEVIR-CD"

# Hugging Face dataset repo — the dataset card links to individual split ZIPs.
# URLs verified 2024-04. Re-check if download fails.
_HF_BASE = "https://huggingface.co/datasets/satellogic/levir-cd/resolve/main"
_SPLITS = ["train", "val", "test"]


def _download_file(url: str, dest: Path, chunk_size: int = 1 << 20) -> None:
    """Stream-download *url* to *dest*, skipping if already present."""
    if dest.exists():
        logger.info("Already downloaded: %s — skipping", dest.name)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s → %s", url, dest)

    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {downloaded >> 20} / {total >> 20} MB  ({pct:.0f}%)", end="", flush=True)
    print()
    logger.info("Downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)


def _unzip(archive: Path, dest_dir: Path) -> None:
    logger.info("Extracting %s → %s", archive.name, dest_dir)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest_dir)
    archive.unlink()
    logger.info("Extracted and removed archive")


def download(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "_downloads"
    tmp.mkdir(exist_ok=True)

    for split in _SPLITS:
        url = f"{_HF_BASE}/{split}.zip"
        archive = tmp / f"{split}.zip"
        try:
            _download_file(url, archive)
            _unzip(archive, dest)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Failed to download %s split: HTTP %d\n"
                "Try downloading manually from https://justchenhao.github.io/LEVIR/ "
                "or https://huggingface.co/datasets/satellogic/levir-cd",
                split, exc.response.status_code,
            )
            raise

    tmp.rmdir()
    logger.info("LEVIR-CD ready at %s", dest)
    _print_summary(dest)


def _print_summary(root: Path) -> None:
    for split in _SPLITS:
        a_dir = root / split / "A"
        if a_dir.exists():
            n = sum(1 for _ in a_dir.iterdir())
            logger.info("  %s: %d pairs", split, n)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Download LEVIR-CD dataset")
    p.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Destination directory")
    args = p.parse_args()
    download(args.dest)
