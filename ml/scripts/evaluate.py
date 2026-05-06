"""Evaluate a checkpoint on the LEVIR-CD test split.

Usage:
    python ml/scripts/evaluate.py \\
        --checkpoint ml/checkpoints/siamese_unet_v2.pth \\
        --data-dir ml/data/LEVIR-CD/test \\
        --threshold 0.35 \\
        --output-dir ml/eval_outputs/baseline/

Outputs:
    <output-dir>/metrics.json          — overall IoU, F1, precision, recall
    <output-dir>/per_pair.json         — per-image metrics
    <output-dir>/best_5/               — side-by-side PNGs for 5 best pairs
    <output-dir>/worst_5/              — side-by-side PNGs for 5 worst pairs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_scripts_dir = Path(__file__).resolve().parent
_ml_dir = _scripts_dir.parent
_repo_root = _ml_dir.parent

sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_ml_dir))

try:
    from ml.app.inference import ChangeDetector, SiameseUNet
except ModuleNotFoundError:
    from app.inference import ChangeDetector, SiameseUNet


def compute_metrics(pred: np.ndarray, gt: np.ndarray) -> dict[str, float]:
    """Compute pixel-level IoU, F1, precision, recall."""
    tp = float((pred & gt).sum())
    fp = float((pred & ~gt).sum())
    fn = float((~pred & gt).sum())
    tn = float((~pred & ~gt).sum())

    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    iou = tp / (tp + fp + fn + 1e-8)

    return {
        "iou": round(iou, 4),
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }


def make_panel(
    a_path: Path,
    b_path: Path,
    gt: np.ndarray,
    pred_mask: np.ndarray,
    metrics: dict,
    title: str,
) -> Image.Image:
    """Build a 4-panel side-by-side comparison image."""
    size = 256

    def load(p: Path) -> Image.Image:
        return Image.open(p).convert("RGB").resize((size, size), Image.BILINEAR)

    t1 = load(a_path)
    t2 = load(b_path)

    def mask_to_rgb(m: np.ndarray, color: tuple) -> Image.Image:
        rgba = np.zeros((size, size, 3), dtype=np.uint8)
        rgba[m] = color
        return Image.fromarray(rgba)

    gt_img = mask_to_rgb(gt, (0, 200, 0))
    pred_img = mask_to_rgb(pred_mask, (200, 50, 50))

    panel_w = size * 4 + 10
    panel_h = size + 40
    panel = Image.new("RGB", (panel_w, panel_h), (30, 30, 30))

    panel.paste(t1, (0, 40))
    panel.paste(t2, (size, 40))
    panel.paste(gt_img, (size * 2, 40))
    panel.paste(pred_img, (size * 3, 40))

    draw = ImageDraw.Draw(panel)
    header = (
        f"{title}  |  IoU={metrics['iou']:.3f}  F1={metrics['f1']:.3f}  "
        f"P={metrics['precision']:.3f}  R={metrics['recall']:.3f}"
    )
    draw.text((4, 4), header, fill=(220, 220, 220))

    labels = ["T1 (before)", "T2 (after)", "GT (green)", "Pred (red)"]
    for i, label in enumerate(labels):
        draw.text((i * size + 4, size + 42), label, fill=(180, 180, 180))

    return panel


def evaluate(
    checkpoint: Path,
    data_dir: Path,
    threshold: float,
    output_dir: Path,
    split: str = "test",
    dropout: float = 0.0,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "best_5").mkdir(exist_ok=True)
    (output_dir / "worst_5").mkdir(exist_ok=True)

    detector = ChangeDetector(
        checkpoint_path=checkpoint,
        threshold=threshold,
    )

    # Support both flat layout (root/A/{split}_*.png) and split-subdir layout.
    flat_a = data_dir / "A"
    subdir_a = data_dir / split / "A"

    if subdir_a.exists():
        a_dir = subdir_a
        b_dir = data_dir / split / "B"
        lbl_dir = data_dir / split / "label"
        pairs = sorted(a_dir.glob("*.png"))
    elif flat_a.exists():
        a_dir = flat_a
        b_dir = data_dir / "B"
        lbl_dir = data_dir / "label"
        pairs = sorted(p for p in a_dir.glob("*.png") if p.stem.startswith(split))
    else:
        raise FileNotFoundError(f"Cannot find LEVIR-CD data under {data_dir}")

    print(f"Evaluating {len(pairs)} pairs from {data_dir} (threshold={threshold})")

    per_pair = []
    for a_path in pairs:
        name = a_path.name
        b_path = b_dir / name
        lbl_path = lbl_dir / name

        if not b_path.exists() or not lbl_path.exists():
            print(f"  skip {name}: missing B or label")
            continue

        prob = detector.predict_mask(str(a_path), str(b_path))
        pred_bool = prob >= threshold

        lbl_arr = np.array(Image.open(lbl_path).convert("L").resize((256, 256), Image.NEAREST))
        gt_bool = lbl_arr > 128

        m = compute_metrics(pred_bool, gt_bool)
        m["name"] = name
        per_pair.append(m)

    if not per_pair:
        print("ERROR: no pairs evaluated")
        return {}

    # Aggregate metrics (mean over all pairs).
    keys = ["iou", "f1", "precision", "recall"]
    overall = {k: round(float(np.mean([p[k] for p in per_pair])), 4) for k in keys}
    overall["n_pairs"] = len(per_pair)
    overall["threshold"] = threshold
    overall["checkpoint"] = str(checkpoint)

    print(f"\nOverall metrics ({len(per_pair)} pairs):")
    for k in keys:
        print(f"  {k:12s}: {overall[k]:.4f}")

    # Save JSON outputs.
    (output_dir / "metrics.json").write_text(json.dumps(overall, indent=2))
    (output_dir / "per_pair.json").write_text(json.dumps(per_pair, indent=2))

    # Save panels for best and worst 5 pairs by IoU.
    sorted_pairs = sorted(per_pair, key=lambda p: p["iou"])
    worst_5 = sorted_pairs[:5]
    best_5 = sorted_pairs[-5:]

    for group_name, group in [("worst_5", worst_5), ("best_5", best_5)]:
        for entry in group:
            name = entry["name"]
            a_path = a_dir / name
            b_path = b_dir / name
            lbl_path = lbl_dir / name

            prob = detector.predict_mask(str(a_path), str(b_path))
            pred_bool = prob >= threshold
            lbl_arr = np.array(Image.open(lbl_path).convert("L").resize((256, 256), Image.NEAREST))
            gt_bool = lbl_arr > 128

            panel = make_panel(a_path, b_path, gt_bool, pred_bool, entry, name)
            panel.save(output_dir / group_name / name)

    print(f"\nSaved panels to {output_dir}/best_5/ and {output_dir}/worst_5/")
    print(f"Saved metrics to {output_dir}/metrics.json")

    return overall


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--data-dir", type=Path, required=True,
                   help="Directory containing A/, B/, label/ subdirs (test split)")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--split", type=str, default="test",
                   help="Which split to evaluate (default: test)")
    p.add_argument("--dropout", type=float, default=0.0)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    evaluate(
        checkpoint=args.checkpoint,
        data_dir=args.data_dir,
        threshold=args.threshold,
        output_dir=args.output_dir,
        split=args.split,
        dropout=args.dropout,
    )
