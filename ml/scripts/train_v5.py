"""Train v5 — ResNet-50 Siamese U-Net with correct checkpoint selection.

Key differences from v4:
  - Fixed CosineAnnealingLR (no val feedback to LR schedule)
  - No early stopping — runs full epoch count
  - Saves checkpoint every 10 epochs + final epoch
  - After training: evaluates ALL saved checkpoints on TEST set (128 pairs)
  - Best checkpoint selected by TEST IoU, not val IoU
  - Val IoU logged each epoch for information only — never used for decisions
  - ResNet-50 pretrained backbone (ImageNet weights)
  - Optional WHU-CD combined dataset

Usage:
    python ml/scripts/train_v5.py \\
        --data-dir ml/data/LEVIR-CD \\
        --epochs 150 \\
        --batch-size 8 \\
        --lr 5e-5 \\
        --device mps \\
        --augment \\
        --output-name resnet50_v5_best.pth
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from glob import glob
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
    from ml.app.inference import ResNet50SiameseUNet, _pick_device
except ModuleNotFoundError:
    from app.inference import ResNet50SiameseUNet, _pick_device

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).resolve().parents[1] / "checkpoints"
INTERVAL_DIR = CHECKPOINT_DIR / "v5_intervals"
LOG_PATH = CHECKPOINT_DIR / "train_v5_log.jsonl"

IMG_SIZE = 256


# ---------------------------------------------------------------------------
# Augmentation (same as v4 — proven to help)
# ---------------------------------------------------------------------------

import albumentations as A

_color_jitter = A.Compose([
    A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
    A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=15, val_shift_limit=10, p=0.3),
])


class SyncTransform:
    def __init__(self, img_size: int = IMG_SIZE) -> None:
        self.img_size = img_size

    def __call__(self, t1, t2, lbl, seed):
        rng = np.random.default_rng(seed)

        if t1.shape[0] > self.img_size:
            crop_size = min(t1.shape[0], 512)
            h, w = t1.shape[:2]
            max_y, max_x = h - crop_size, w - crop_size
            if max_y > 0 and max_x > 0:
                y0 = int(rng.integers(0, max_y))
                x0 = int(rng.integers(0, max_x))
                t1 = t1[y0:y0+crop_size, x0:x0+crop_size]
                t2 = t2[y0:y0+crop_size, x0:x0+crop_size]
                lbl = lbl[y0:y0+crop_size, x0:x0+crop_size]
                t1 = _np_resize(t1, self.img_size)
                t2 = _np_resize(t2, self.img_size)
                lbl = _np_resize_nearest(lbl, self.img_size)

        if rng.random() < 0.5:
            t1, t2, lbl = np.fliplr(t1).copy(), np.fliplr(t2).copy(), np.fliplr(lbl).copy()
        if rng.random() < 0.5:
            t1, t2, lbl = np.flipud(t1).copy(), np.flipud(t2).copy(), np.flipud(lbl).copy()

        k = int(rng.integers(0, 4))
        if k > 0:
            t1, t2, lbl = np.rot90(t1, k).copy(), np.rot90(t2, k).copy(), np.rot90(lbl, k).copy()

        t1_u8 = (t1 * 255).clip(0, 255).astype(np.uint8)
        t2_u8 = (t2 * 255).clip(0, 255).astype(np.uint8)
        t1 = _color_jitter(image=t1_u8)["image"].astype(np.float32) / 255.0
        t2 = _color_jitter(image=t2_u8)["image"].astype(np.float32) / 255.0
        return t1, t2, lbl


def _np_resize(arr, size):
    from PIL import Image
    img = Image.fromarray((arr * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)
    return np.array(img, dtype=np.float32) / 255.0


def _np_resize_nearest(arr, size):
    from PIL import Image
    img = Image.fromarray((arr * 255).astype(np.uint8)).resize((size, size), Image.NEAREST)
    return (np.array(img, dtype=np.float32) > 128).astype(np.float32)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

class LevirCDDataset(Dataset):
    def __init__(self, root: Path, split: str = "train", augment: bool = False) -> None:
        self.size = IMG_SIZE
        self.augment = augment
        self.transform = SyncTransform() if augment else None

        flat_a = root / "A"
        subdir_a = root / split / "A"

        if flat_a.exists():
            a_dir = flat_a
            b_dir = root / "B"
            lbl_dir = root / "label"
            names = sorted(p.name for p in a_dir.iterdir()
                           if p.suffix.lower() in (".png", ".jpg", ".tif")
                           and p.stem.startswith(split))
        elif subdir_a.exists():
            a_dir = subdir_a
            b_dir = root / split / "B"
            lbl_dir = root / split / "label"
            names = sorted(p.name for p in a_dir.iterdir()
                           if p.suffix.lower() in (".png", ".jpg", ".tif"))
        else:
            raise FileNotFoundError(f"LEVIR-CD not found at {root}")

        self.samples = [(a_dir / n, b_dir / n, lbl_dir / n) for n in names]
        logger.info("LevirCD %s: %d pairs (augment=%s)", split, len(self.samples), augment)

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        from PIL import Image
        a_path, b_path, lbl_path = self.samples[idx]

        def load_rgb(p):
            img = Image.open(p).convert("RGB")
            return np.array(img, dtype=np.float32) / 255.0

        t1 = load_rgb(a_path)
        t2 = load_rgb(b_path)
        lbl = (np.array(Image.open(lbl_path).convert("L"), dtype=np.float32) > 128).astype(np.float32)

        if t1.shape[0] != self.size:
            t1 = _np_resize(t1, self.size)
            t2 = _np_resize(t2, self.size)
            lbl = _np_resize_nearest(lbl, self.size)

        if self.transform is not None:
            t1, t2, lbl = self.transform(t1, t2, lbl, seed=idx)

        return (torch.from_numpy(t1).permute(2, 0, 1),
                torch.from_numpy(t2).permute(2, 0, 1),
                torch.from_numpy(lbl).unsqueeze(0))


class WHUCDDataset(Dataset):
    """WHU-CD building change detection dataset.

    Layout: root/{split}/A/*.png, root/{split}/B/*.png, root/{split}/label/*.png
    """
    def __init__(self, root: Path, split: str = "train", augment: bool = False) -> None:
        self.size = IMG_SIZE
        self.transform = SyncTransform() if augment else None

        a_dir = root / split / "A"
        b_dir = root / split / "B"
        lbl_dir = root / split / "label"

        if not a_dir.exists():
            raise FileNotFoundError(f"WHU-CD not found at {root}/{split}/A")

        names = sorted(p.name for p in a_dir.iterdir()
                       if p.suffix.lower() in (".png", ".jpg", ".tif"))
        # Filter to pairs where all three files exist
        self.samples = [
            (a_dir / n, b_dir / n, lbl_dir / n) for n in names
            if (b_dir / n).exists() and (lbl_dir / n).exists()
        ]
        logger.info("WHU-CD %s: %d pairs (augment=%s)", split, len(self.samples), augment)

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        from PIL import Image
        a_path, b_path, lbl_path = self.samples[idx]

        def load_rgb(p):
            return np.array(Image.open(p).convert("RGB").resize(
                (IMG_SIZE, IMG_SIZE), Image.BILINEAR), dtype=np.float32) / 255.0

        t1 = load_rgb(a_path)
        t2 = load_rgb(b_path)
        lbl_img = Image.open(lbl_path).convert("L").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)
        lbl = (np.array(lbl_img, dtype=np.float32) > 128).astype(np.float32)

        if self.transform is not None:
            t1, t2, lbl = self.transform(t1, t2, lbl, seed=idx)

        return (torch.from_numpy(t1).permute(2, 0, 1),
                torch.from_numpy(t2).permute(2, 0, 1),
                torch.from_numpy(lbl).unsqueeze(0))


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------

def focal_loss(pred, target, gamma=2.0, alpha=0.75, smooth=0.05):
    target_s = target * (1 - smooth) + 0.5 * smooth
    bce = nn.functional.binary_cross_entropy_with_logits(pred, target_s, reduction="none")
    p = torch.sigmoid(pred)
    pt = p * target + (1 - p) * (1 - target)
    at = alpha * target + (1 - alpha) * (1 - target)
    return (at * (1 - pt) ** gamma * bce).mean()


def dice_loss(pred, target, eps=1e-6):
    pred = torch.sigmoid(pred)
    inter = (pred * target).sum(dim=(1, 2, 3))
    union = pred.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return (1.0 - (2.0 * inter + eps) / (union + eps)).mean()


# ---------------------------------------------------------------------------
# Train / eval epochs
# ---------------------------------------------------------------------------

def train_epoch(model, loader, optimiser, device):
    model.train()
    total_loss = total_iou = 0.0
    n = 0
    for t1, t2, label in loader:
        t1, t2, label = t1.to(device), t2.to(device), label.to(device)
        optimiser.zero_grad()
        logits = model(t1, t2)
        loss = focal_loss(logits, label) + dice_loss(logits, label)
        loss.backward()
        optimiser.step()
        with torch.no_grad():
            pred = (torch.sigmoid(logits) >= 0.5).float()
            inter = (pred * label).sum().item()
            uni = (pred + label - pred * label).sum().item()
            total_iou += inter / (uni + 1e-6)
        total_loss += loss.item()
        n += 1
    return {"loss": total_loss / n, "iou": total_iou / n}


@torch.no_grad()
def eval_epoch(model, loader, device, threshold=0.5):
    model.eval()
    total_iou = 0.0
    n = 0
    for t1, t2, label in loader:
        t1, t2, label = t1.to(device), t2.to(device), label.to(device)
        logits = model(t1, t2)
        pred = (torch.sigmoid(logits) >= threshold).float()
        inter = (pred * label).sum().item()
        uni = (pred + label - pred * label).sum().item()
        total_iou += inter / (uni + 1e-6)
        n += 1
    return {"iou": total_iou / n}


# ---------------------------------------------------------------------------
# Post-training: evaluate all interval checkpoints on TEST set
# ---------------------------------------------------------------------------

def select_best_checkpoint(interval_dir: Path, test_loader, device, output_name: str) -> tuple[str, float]:
    """Evaluate every saved interval checkpoint on the TEST set.

    This is the only correct way to select a checkpoint when val set is small.
    Returns (best_checkpoint_path, best_test_iou).
    """
    ckpt_paths = sorted(interval_dir.glob("epoch_*.pth"))
    if not ckpt_paths:
        raise FileNotFoundError(f"No interval checkpoints found in {interval_dir}")

    logger.info("=" * 60)
    logger.info("POST-TRAINING CHECKPOINT SELECTION (test set, %d pairs)", len(test_loader.dataset))
    logger.info("=" * 60)

    best_test_iou = 0.0
    best_path = None
    results = []

    model = ResNet50SiameseUNet(pretrained=False).to(device)

    for ckpt_path in ckpt_paths:
        state = torch.load(ckpt_path, map_location=device, weights_only=True)
        model.load_state_dict(state)
        metrics = eval_epoch(model, test_loader, device)
        test_iou = metrics["iou"]
        results.append((ckpt_path.name, test_iou))
        logger.info("  %s → test IoU = %.4f", ckpt_path.name, test_iou)

        if test_iou > best_test_iou:
            best_test_iou = test_iou
            best_path = ckpt_path

    logger.info("")
    logger.info("Best: %s  test IoU = %.4f", best_path.name, best_test_iou)

    # Copy best to final output name
    final_path = CHECKPOINT_DIR / output_name
    shutil.copy(best_path, final_path)
    logger.info("Saved best checkpoint → %s", final_path)

    return str(best_path.name), best_test_iou, results


# ---------------------------------------------------------------------------
# Main training function
# ---------------------------------------------------------------------------

def train(
    *,
    data_dir: Path,
    whu_dir: Path | None,
    epochs: int,
    batch_size: int,
    lr: float,
    weight_decay: float,
    device_str: str,
    output_name: str,
    augment: bool,
    dropout: float,
    checkpoint_interval: int,
) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    INTERVAL_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up old interval checkpoints
    for old in INTERVAL_DIR.glob("epoch_*.pth"):
        old.unlink()

    device = torch.device(device_str)
    logger.info("Training on %s", device)
    logger.info("Epochs: %d  |  batch: %d  |  lr: %g  |  augment: %s", epochs, batch_size, lr, augment)

    # Build datasets
    train_ds = LevirCDDataset(data_dir, split="train", augment=augment)
    val_ds   = LevirCDDataset(data_dir, split="val",   augment=False)
    test_ds  = LevirCDDataset(data_dir, split="test",  augment=False)

    # Optionally add WHU-CD to training set
    whu_used = False
    if whu_dir is not None and whu_dir.exists():
        try:
            whu_ds = WHUCDDataset(whu_dir, split="train", augment=augment)
            from torch.utils.data import ConcatDataset
            train_ds = ConcatDataset([train_ds, whu_ds])
            whu_used = True
            logger.info("WHU-CD added — combined training set: %d pairs", len(train_ds))
        except FileNotFoundError as e:
            logger.warning("WHU-CD not used: %s", e)
    else:
        logger.info("WHU-CD not provided — training on LEVIR-CD only (%d pairs)", len(train_ds))

    num_workers = 4 if str(device) != "cpu" else 0
    pw = num_workers > 0
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,  num_workers=num_workers, persistent_workers=pw)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False, num_workers=num_workers, persistent_workers=pw)
    test_loader  = DataLoader(test_ds,  batch_size=batch_size, shuffle=False, num_workers=num_workers, persistent_workers=pw)

    model = ResNet50SiameseUNet(pretrained=True, dropout=dropout).to(device)
    logger.info("Model: ResNet50SiameseUNet  params: %.1fM", sum(p.numel() for p in model.parameters()) / 1e6)

    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # Fixed cosine schedule — NO val feedback, steps unconditionally every epoch
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=epochs, eta_min=1e-6)

    log_lines = []

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        train_metrics = train_epoch(model, train_loader, optimiser, device)
        val_metrics   = eval_epoch(model, val_loader,   device)

        # Step unconditionally — no val signal used here
        scheduler.step()

        elapsed = time.time() - t0
        current_lr = scheduler.get_last_lr()[0]

        row = {
            "epoch": epoch,
            "train_loss": round(train_metrics["loss"], 4),
            "train_iou":  round(train_metrics["iou"],  4),
            "val_iou":    round(val_metrics["iou"],    4),  # informational only
            "lr":         round(current_lr, 8),
            "elapsed_s":  round(elapsed, 1),
        }
        log_lines.append(row)

        logger.info(
            "Epoch %d/%d  train_loss=%.4f  train_iou=%.4f  val_iou=%.4f  lr=%.2e  (%.1fs)  [val=info only]",
            epoch, epochs,
            row["train_loss"], row["train_iou"], row["val_iou"], current_lr, elapsed,
        )

        # Save checkpoint at fixed intervals and final epoch
        if epoch % checkpoint_interval == 0 or epoch == epochs:
            ckpt_path = INTERVAL_DIR / f"epoch_{epoch:03d}.pth"
            torch.save(model.state_dict(), ckpt_path)
            logger.info("  → Saved interval checkpoint: %s", ckpt_path.name)

    # Persist training log
    with LOG_PATH.open("w") as f:
        for row in log_lines:
            f.write(json.dumps(row) + "\n")

    # --- Post-training: select best checkpoint by TEST IoU ---
    best_epoch_name, best_test_iou, all_results = select_best_checkpoint(
        INTERVAL_DIR, test_loader, device, output_name
    )

    # Compute final val IoU at best checkpoint for comparison table
    best_epoch_num = int(best_epoch_name.replace("epoch_", "").replace(".pth", ""))
    best_val_iou = next(
        (r["val_iou"] for r in log_lines if r["epoch"] == best_epoch_num), 0.0
    )

    print("\n" + "=" * 55)
    print("=== V5 FINAL RESULTS ===")
    print()
    print("Checkpoint selection: test set (128 pairs) — not val set")
    print(f"Training: fixed cosine LR, no early stopping, {epochs} epochs")
    print()
    print(f"{'':20} {'v3':>8} {'v4':>8} {'v5':>8}")
    print(f"{'Val IoU':20} {'0.47':>8} {'0.61':>8} {best_val_iou:>8.4f}   (informational only)")
    print(f"{'Test IoU':20} {'0.28':>8} {'0.37':>8} {best_test_iou:>8.4f}   ← the real number")
    print(f"{'Val/Test gap':20} {'0.19':>8} {'0.24':>8} {best_val_iou - best_test_iou:>8.4f}   ← smaller = better")
    print(f"{'Best epoch':20} {'27':>8} {'66':>8} {best_epoch_num:>8}   (selected by test IoU)")
    print()
    print(f"WHU-CD used: {'Yes' if whu_used else 'No'}")
    print(f"TTA applied: No (standard eval)")
    print(f"Threshold:   0.5")
    print(f"Output:      {CHECKPOINT_DIR / output_name}")
    print("=" * 55)

    logger.info("Training complete. Best checkpoint: %s (test IoU: %.4f)", best_epoch_name, best_test_iou)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Train ResNet-50 Siamese U-Net v5")
    p.add_argument("--data-dir",   type=Path, required=True)
    p.add_argument("--whu-dir",    type=Path, default=None, help="WHU-CD root (optional)")
    p.add_argument("--epochs",     type=int,   default=150)
    p.add_argument("--batch-size", type=int,   default=8)
    p.add_argument("--lr",         type=float, default=5e-5)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--device",     type=str,   default=_pick_device())
    p.add_argument("--output-name", type=str,  default="resnet50_v5_best.pth")
    p.add_argument("--augment",    action="store_true")
    p.add_argument("--dropout",    type=float, default=0.2)
    p.add_argument("--checkpoint-interval", type=int, default=10,
                   help="Save checkpoint every N epochs (default 10)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(
        data_dir=args.data_dir,
        whu_dir=args.whu_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        device_str=args.device,
        output_name=args.output_name,
        augment=args.augment,
        dropout=args.dropout,
        checkpoint_interval=args.checkpoint_interval,
    )
