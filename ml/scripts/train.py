"""Train a Siamese U-Net for binary change detection.

Usage — quick smoke test on synthetic data (no download required):
    python ml/scripts/train.py --synthetic --epochs 3

Usage — LEVIR-CD dataset (download first with download_levir.py):
    python ml/scripts/train.py --data-dir ml/data/LEVIR-CD --epochs 10

The synthetic dataset generates random 256×256 image pairs where a random
rectangle is "added" in T2 — a controlled proxy for a new building.  It is
intended only to verify the training loop runs and produce a checkpoint that
the ml-service can load.  Accuracy on real imagery will be poor until you
train on LEVIR-CD or Rwandan satellite data.

Output:
    ml/checkpoints/siamese_unet_levir_v0.pth   — model state dict
    ml/checkpoints/train_log.jsonl             — per-epoch metrics
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Iterator

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Add the repo root to sys.path so we can import ml.app.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.app.inference import SiameseUNet, _pick_device  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).resolve().parents[1] / "checkpoints"
# Default output name — overridden via --output-name CLI flag.
_DEFAULT_CHECKPOINT_NAME = "siamese_unet_v1.pth"
LOG_PATH = CHECKPOINT_DIR / "train_log.jsonl"

IMG_SIZE = 256


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


class SyntheticChangeDataset(Dataset):
    """Generates image pairs on the fly with synthetic rectangular changes.

    Each sample is:
      t1: (3, H, W) — baseline scene (random texture)
      t2: (3, H, W) — same scene but with 0–3 random bright rectangles added
      label: (1, H, W) — binary mask of changed pixels
    """

    def __init__(self, n_samples: int = 512, img_size: int = IMG_SIZE, seed: int = 42) -> None:
        self.n = n_samples
        self.size = img_size
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        rng = np.random.default_rng(idx)  # deterministic per index

        # Base texture: smooth noise so the model can't just memorize pixel values.
        base = rng.random((self.size, self.size, 3), dtype=np.float32)
        t1 = base.copy()
        t2 = base.copy()
        label = np.zeros((self.size, self.size), dtype=np.float32)

        n_changes = rng.integers(0, 4)  # 0–3 rectangles
        for _ in range(n_changes):
            h = rng.integers(20, 80)
            w = rng.integers(20, 80)
            y0 = rng.integers(0, self.size - h)
            x0 = rng.integers(0, self.size - w)
            colour = rng.random(3, dtype=np.float32) * 0.4 + 0.6  # bright-ish
            t2[y0:y0 + h, x0:x0 + w] = colour
            label[y0:y0 + h, x0:x0 + w] = 1.0

        t1_t = torch.from_numpy(t1).permute(2, 0, 1)
        t2_t = torch.from_numpy(t2).permute(2, 0, 1)
        lbl_t = torch.from_numpy(label).unsqueeze(0)

        return t1_t, t2_t, lbl_t


class LevirCDDataset(Dataset):
    """Load image pairs from a LEVIR-CD directory.

    Supports two layouts:

    1. Torchgeo flat layout (downloaded via torchgeo's LEVIRCD.download=True):
         root/A/{split}_*.png
         root/B/{split}_*.png
         root/label/{split}_*.png

    2. Split-subdirectory layout (original download_levir.py script):
         root/{split}/A/*.png
         root/{split}/B/*.png
         root/{split}/label/*.png
    """

    def __init__(self, root: Path, split: str = "train", img_size: int = IMG_SIZE) -> None:
        self.size = img_size

        # Detect layout: torchgeo flat (root/A/) vs split-subdir (root/split/A/)
        flat_a = root / "A"
        subdir_a = root / split / "A"

        if flat_a.exists():
            # Torchgeo layout: filter by split prefix in filename
            a_dir, b_dir, lbl_dir = flat_a, root / "B", root / "label"
            names = sorted(
                p.name for p in a_dir.iterdir()
                if p.suffix.lower() in (".png", ".jpg", ".tif")
                and p.stem.startswith(split)
            )
        elif subdir_a.exists():
            a_dir, b_dir, lbl_dir = subdir_a, root / split / "B", root / split / "label"
            names = sorted(
                p.name for p in a_dir.iterdir()
                if p.suffix.lower() in (".png", ".jpg", ".tif")
            )
        else:
            raise FileNotFoundError(
                f"LEVIR-CD directory not found at {root}\n"
                "Run: python ml/scripts/train.py --synthetic  OR\n"
                "     python -c \"from torchgeo.datasets import LEVIRCD; LEVIRCD(root='ml/data/LEVIR-CD', split='train', download=True)\""
            )

        self.samples = [(a_dir / n, b_dir / n, lbl_dir / n) for n in names]
        logger.info("LevirCDDataset: %s split, %d pairs from %s", split, len(self.samples), root)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        from PIL import Image

        a_path, b_path, lbl_path = self.samples[idx]

        def load(p: Path) -> np.ndarray:
            img = Image.open(p).convert("RGB").resize((self.size, self.size), Image.BILINEAR)
            return np.array(img, dtype=np.float32) / 255.0

        t1 = load(a_path)
        t2 = load(b_path)

        lbl_img = Image.open(lbl_path).convert("L").resize((self.size, self.size), Image.NEAREST)
        lbl = (np.array(lbl_img, dtype=np.float32) > 128).astype(np.float32)

        t1_t = torch.from_numpy(t1).permute(2, 0, 1)
        t2_t = torch.from_numpy(t2).permute(2, 0, 1)
        lbl_t = torch.from_numpy(lbl).unsqueeze(0)

        return t1_t, t2_t, lbl_t


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------


def dice_loss(pred: torch.Tensor, target: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    pred = torch.sigmoid(pred)
    intersection = (pred * target).sum(dim=(1, 2, 3))
    union = pred.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return 1.0 - (2.0 * intersection + eps) / (union + eps)


def train_epoch(
    model: SiameseUNet,
    loader: DataLoader,
    optimiser: torch.optim.Optimizer,
    device: torch.device,
) -> dict[str, float]:
    model.train()
    bce = nn.BCEWithLogitsLoss()
    total_loss = total_dice = total_iou = 0.0
    n = 0

    for t1, t2, label in loader:
        t1, t2, label = t1.to(device), t2.to(device), label.to(device)
        optimiser.zero_grad()
        logits = model(t1, t2)
        loss = bce(logits, label) + dice_loss(logits, label).mean()
        loss.backward()
        optimiser.step()

        with torch.no_grad():
            pred = (torch.sigmoid(logits) >= 0.5).float()
            inter = (pred * label).sum().item()
            uni = (pred + label - pred * label).sum().item()
            iou = inter / (uni + 1e-6)

        total_loss += loss.item()
        total_dice += (1 - dice_loss(logits.detach(), label).mean().item())
        total_iou += iou
        n += 1

    return {
        "loss": total_loss / n,
        "dice": total_dice / n,
        "iou": total_iou / n,
    }


@torch.no_grad()
def eval_epoch(
    model: SiameseUNet,
    loader: DataLoader,
    device: torch.device,
) -> dict[str, float]:
    model.eval()
    bce = nn.BCEWithLogitsLoss()
    total_loss = total_iou = 0.0
    n = 0

    for t1, t2, label in loader:
        t1, t2, label = t1.to(device), t2.to(device), label.to(device)
        logits = model(t1, t2)
        loss = bce(logits, label) + dice_loss(logits, label).mean()
        pred = (torch.sigmoid(logits) >= 0.5).float()
        inter = (pred * label).sum().item()
        uni = (pred + label - pred * label).sum().item()
        total_loss += loss.item()
        total_iou += inter / (uni + 1e-6)
        n += 1

    return {"loss": total_loss / n, "iou": total_iou / n}


def train(
    *,
    data_dir: Path | None,
    synthetic: bool,
    epochs: int,
    batch_size: int,
    lr: float,
    device_str: str,
    output_name: str = _DEFAULT_CHECKPOINT_NAME,
) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / output_name

    device = torch.device(device_str)
    logger.info("Training on %s", device)

    if synthetic or data_dir is None:
        logger.info("Using synthetic dataset (no real imagery required)")
        train_ds = SyntheticChangeDataset(n_samples=512, seed=42)
        val_ds = SyntheticChangeDataset(n_samples=64, seed=99)
    else:
        logger.info("Loading LEVIR-CD from %s", data_dir)
        train_ds = LevirCDDataset(data_dir, split="train")
        val_ds = LevirCDDataset(data_dir, split="test")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    model = SiameseUNet(base_ch=32).to(device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=epochs)

    best_iou = 0.0
    log_lines: list[dict] = []

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        train_metrics = train_epoch(model, train_loader, optimiser, device)
        val_metrics = eval_epoch(model, val_loader, device)
        scheduler.step()
        elapsed = time.time() - t0

        row = {
            "epoch": epoch,
            "train_loss": round(train_metrics["loss"], 4),
            "train_dice": round(train_metrics["dice"], 4),
            "train_iou": round(train_metrics["iou"], 4),
            "val_loss": round(val_metrics["loss"], 4),
            "val_iou": round(val_metrics["iou"], 4),
            "elapsed_s": round(elapsed, 1),
        }
        log_lines.append(row)

        logger.info(
            "Epoch %d/%d  train_loss=%.4f  train_iou=%.4f  val_iou=%.4f  (%.1fs)",
            epoch, epochs,
            row["train_loss"], row["train_iou"], row["val_iou"], elapsed,
        )

        if val_metrics["iou"] > best_iou:
            best_iou = val_metrics["iou"]
            torch.save(model.state_dict(), checkpoint_path)
            logger.info("  → Saved new best checkpoint (val_iou=%.4f)", best_iou)

    # Write training log.
    with LOG_PATH.open("w") as f:
        for row in log_lines:
            f.write(json.dumps(row) + "\n")

    logger.info("Training complete. Best val IoU: %.4f", best_iou)
    logger.info("Checkpoint: %s", checkpoint_path)
    logger.info("Log:        %s", LOG_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train Siamese U-Net for change detection")
    p.add_argument("--data-dir", type=Path, default=None, help="Path to LEVIR-CD directory")
    p.add_argument("--synthetic", action="store_true", help="Use synthetic dataset (ignores --data-dir)")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", type=str, default=_pick_device())
    p.add_argument("--output-name", type=str, default=_DEFAULT_CHECKPOINT_NAME,
                   help="Checkpoint filename (saved under ml/checkpoints/)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        data_dir=args.data_dir,
        synthetic=args.synthetic or args.data_dir is None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device_str=args.device,
        output_name=args.output_name,
    )
