"""Train a Siamese U-Net for binary change detection.

Usage — quick smoke test on synthetic data (no download required):
    python ml/scripts/train.py --synthetic --epochs 3

Usage — LEVIR-CD dataset:
    python ml/scripts/train.py --data-dir ml/data/LEVIR-CD --epochs 30 \\
        --augment --dropout 0.3 --early-stopping-patience 8 \\
        --output-name siamese_unet_v3.pth

Output:
    ml/checkpoints/<output-name>   — best model state dict (by val IoU)
    ml/checkpoints/train_log.jsonl — per-epoch metrics (JSONL)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

import sys

_scripts_dir = Path(__file__).resolve().parent
_ml_dir = _scripts_dir.parent
_repo_root = _ml_dir.parent

sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_ml_dir))

try:
    from ml.app.inference import SiameseUNet, _pick_device
except ModuleNotFoundError:
    from app.inference import SiameseUNet, _pick_device

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).resolve().parents[1] / "checkpoints"
_DEFAULT_CHECKPOINT_NAME = "siamese_unet_v1.pth"
LOG_PATH = CHECKPOINT_DIR / "train_log.jsonl"

IMG_SIZE = 256


# ---------------------------------------------------------------------------
# Augmentation — synced transforms applied identically to T1, T2, and label
# ---------------------------------------------------------------------------


class SyncTransform:
    """Apply the same random spatial transforms to T1, T2, and label.

    All three must receive identical transforms or the change signal is destroyed.
    Each call uses a per-sample seed so results are deterministic given the index.
    """

    def __init__(self, img_size: int = IMG_SIZE, enable_crop: bool = True) -> None:
        self.img_size = img_size
        self.enable_crop = enable_crop

    def __call__(
        self,
        t1: np.ndarray,
        t2: np.ndarray,
        lbl: np.ndarray,
        seed: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = np.random.default_rng(seed)

        # Random crop from native resolution → 512 → resize to 256.
        # Only applied when the image is larger than the target size.
        if self.enable_crop and t1.shape[0] > self.img_size:
            crop_size = min(t1.shape[0], 512)
            h, w = t1.shape[:2]
            max_y = h - crop_size
            max_x = w - crop_size
            if max_y > 0 and max_x > 0:
                y0 = int(rng.integers(0, max_y))
                x0 = int(rng.integers(0, max_x))
                t1 = t1[y0:y0 + crop_size, x0:x0 + crop_size]
                t2 = t2[y0:y0 + crop_size, x0:x0 + crop_size]
                lbl = lbl[y0:y0 + crop_size, x0:x0 + crop_size]
                # Resize crop to model input size.
                t1 = _np_resize(t1, self.img_size)
                t2 = _np_resize(t2, self.img_size)
                lbl = _np_resize_nearest(lbl, self.img_size)

        # Random horizontal flip (p=0.5).
        if rng.random() < 0.5:
            t1 = np.fliplr(t1).copy()
            t2 = np.fliplr(t2).copy()
            lbl = np.fliplr(lbl).copy()

        # Random vertical flip (p=0.5).
        if rng.random() < 0.5:
            t1 = np.flipud(t1).copy()
            t2 = np.flipud(t2).copy()
            lbl = np.flipud(lbl).copy()

        # Random 90° rotation (uniform over 0°, 90°, 180°, 270°).
        k = int(rng.integers(0, 4))
        if k > 0:
            t1 = np.rot90(t1, k).copy()
            t2 = np.rot90(t2, k).copy()
            lbl = np.rot90(lbl, k).copy()

        return t1, t2, lbl


def _np_resize(arr: np.ndarray, size: int) -> np.ndarray:
    from PIL import Image
    img = Image.fromarray((arr * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)
    return np.array(img, dtype=np.float32) / 255.0


def _np_resize_nearest(arr: np.ndarray, size: int) -> np.ndarray:
    from PIL import Image
    img = Image.fromarray((arr * 255).astype(np.uint8)).resize((size, size), Image.NEAREST)
    return (np.array(img, dtype=np.float32) > 128).astype(np.float32)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


class SyntheticChangeDataset(Dataset):
    def __init__(self, n_samples: int = 512, img_size: int = IMG_SIZE, seed: int = 42) -> None:
        self.n = n_samples
        self.size = img_size
        self.rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        rng = np.random.default_rng(idx)

        base = rng.random((self.size, self.size, 3), dtype=np.float32)
        t1 = base.copy()
        t2 = base.copy()
        label = np.zeros((self.size, self.size), dtype=np.float32)

        n_changes = rng.integers(0, 4)
        for _ in range(n_changes):
            h = rng.integers(20, 80)
            w = rng.integers(20, 80)
            y0 = rng.integers(0, self.size - h)
            x0 = rng.integers(0, self.size - w)
            colour = rng.random(3, dtype=np.float32) * 0.4 + 0.6
            t2[y0:y0 + h, x0:x0 + w] = colour
            label[y0:y0 + h, x0:x0 + w] = 1.0

        t1_t = torch.from_numpy(t1).permute(2, 0, 1)
        t2_t = torch.from_numpy(t2).permute(2, 0, 1)
        lbl_t = torch.from_numpy(label).unsqueeze(0)

        return t1_t, t2_t, lbl_t


class LevirCDDataset(Dataset):
    """Load image pairs from a LEVIR-CD directory.

    Supports two layouts:
    1. Torchgeo flat layout: root/A/{split}_*.png, root/B/, root/label/
    2. Split-subdirectory layout: root/{split}/A/*.png, root/{split}/B/, ...

    Args:
        augment: Apply SyncTransform (H-flip, V-flip, 90° rot, random crop).
                 Should be True for training, False for val/test.
    """

    def __init__(
        self,
        root: Path,
        split: str = "train",
        img_size: int = IMG_SIZE,
        augment: bool = False,
    ) -> None:
        self.size = img_size
        self.augment = augment
        self.transform = SyncTransform(img_size=img_size) if augment else None

        flat_a = root / "A"
        subdir_a = root / split / "A"

        if flat_a.exists():
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
                "     python -c \"from torchgeo.datasets import LEVIRCD; "
                "LEVIRCD(root='ml/data/LEVIR-CD', split='train', download=True)\""
            )

        self.samples = [(a_dir / n, b_dir / n, lbl_dir / n) for n in names]
        logger.info(
            "LevirCDDataset: %s split, %d pairs from %s (augment=%s)",
            split, len(self.samples), root, augment,
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        from PIL import Image

        a_path, b_path, lbl_path = self.samples[idx]

        def load_rgb(p: Path) -> np.ndarray:
            img = Image.open(p).convert("RGB")
            return np.array(img, dtype=np.float32) / 255.0

        t1 = load_rgb(a_path)
        t2 = load_rgb(b_path)

        lbl_img = Image.open(lbl_path).convert("L")
        lbl = (np.array(lbl_img, dtype=np.float32) > 128).astype(np.float32)

        # Resize to model input size if not already the right shape
        # (augmentation may resize internally; this handles non-augmented path).
        if t1.shape[0] != self.size or t1.shape[1] != self.size:
            t1 = _np_resize(t1, self.size)
            t2 = _np_resize(t2, self.size)
            lbl = _np_resize_nearest(lbl, self.size)

        if self.transform is not None:
            t1, t2, lbl = self.transform(t1, t2, lbl, seed=idx)

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
    total_loss = total_iou = 0.0
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
        total_iou += iou
        n += 1

    return {"loss": total_loss / n, "iou": total_iou / n}


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
    weight_decay: float,
    device_str: str,
    output_name: str = _DEFAULT_CHECKPOINT_NAME,
    augment: bool = False,
    dropout: float = 0.0,
    early_stopping_patience: int = 0,
) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / output_name

    device = torch.device(device_str)
    logger.info("Training on %s", device)

    if synthetic or data_dir is None:
        logger.info("Using synthetic dataset")
        train_ds = SyntheticChangeDataset(n_samples=512, seed=42)
        val_ds = SyntheticChangeDataset(n_samples=64, seed=99)
    else:
        logger.info("Loading LEVIR-CD from %s", data_dir)
        train_ds = LevirCDDataset(data_dir, split="train", augment=augment)
        # FIX: use split="val" for validation, not "test".
        # The test split is reserved for final evaluation only (evaluate.py).
        val_ds = LevirCDDataset(data_dir, split="val", augment=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    model = SiameseUNet(base_ch=32, dropout=dropout).to(device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=epochs)

    best_iou = 0.0
    epochs_no_improve = 0
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
            epochs_no_improve = 0
            torch.save(model.state_dict(), checkpoint_path)
            logger.info("  → Saved new best checkpoint (val_iou=%.4f)", best_iou)
        else:
            epochs_no_improve += 1
            logger.info("  → No improvement for %d epoch(s)", epochs_no_improve)

        if early_stopping_patience > 0 and epochs_no_improve >= early_stopping_patience:
            logger.info(
                "Early stopping: no improvement for %d epochs (patience=%d)",
                epochs_no_improve, early_stopping_patience,
            )
            break

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
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--device", type=str, default=_pick_device())
    p.add_argument("--output-name", type=str, default=_DEFAULT_CHECKPOINT_NAME)
    p.add_argument("--augment", action="store_true",
                   help="Apply synced H-flip, V-flip, 90° rotation, random crop")
    p.add_argument("--dropout", type=float, default=0.0,
                   help="Dropout rate in decoder blocks (0 = disabled)")
    p.add_argument("--early-stopping-patience", type=int, default=0,
                   help="Stop if val IoU doesn't improve for N epochs (0 = disabled)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        data_dir=args.data_dir,
        synthetic=args.synthetic or args.data_dir is None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        device_str=args.device,
        output_name=args.output_name,
        augment=args.augment,
        dropout=args.dropout,
        early_stopping_patience=args.early_stopping_patience,
    )
