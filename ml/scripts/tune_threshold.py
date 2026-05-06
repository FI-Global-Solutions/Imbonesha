"""Sweep detection thresholds on the LEVIR-CD test split and pick the best.

Usage:
    python ml/scripts/tune_threshold.py \\
        --checkpoint ml/checkpoints/siamese_unet_v3.pth \\
        --data-dir ml/data/LEVIR-CD \\
        --output ml/eval_outputs/v3_threshold_analysis.json

Prints a table of IoU / F1 / precision / recall for each threshold candidate,
then recommends the threshold that maximises F1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_scripts_dir = Path(__file__).resolve().parent
_ml_dir = _scripts_dir.parent
_repo_root = _ml_dir.parent

sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_ml_dir))

try:
    from ml.app.inference import ChangeDetector
except ModuleNotFoundError:
    from app.inference import ChangeDetector

THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


def compute_metrics_flat(
    pred_bool: np.ndarray, gt_bool: np.ndarray
) -> dict[str, float]:
    tp = float((pred_bool & gt_bool).sum())
    fp = float((pred_bool & ~gt_bool).sum())
    fn = float((~pred_bool & gt_bool).sum())

    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    iou = tp / (tp + fp + fn + 1e-8)

    return {
        "iou": round(iou, 4),
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
    }


def run(checkpoint: Path, data_dir: Path, output: Path) -> None:
    detector = ChangeDetector(checkpoint_path=checkpoint, threshold=0.5)

    # Support flat layout with test_ prefix.
    a_dir = data_dir / "A"
    b_dir = data_dir / "B"
    lbl_dir = data_dir / "label"

    pairs = sorted(p for p in a_dir.glob("*.png") if p.stem.startswith("test"))
    print(f"Loaded {len(pairs)} test pairs from {data_dir}")
    print("Pre-computing probability maps...")

    prob_maps = []
    gt_masks = []
    for a_path in pairs:
        name = a_path.name
        b_path = b_dir / name
        lbl_path = lbl_dir / name
        if not b_path.exists() or not lbl_path.exists():
            continue
        prob = detector.predict_mask(str(a_path), str(b_path))
        lbl = np.array(Image.open(lbl_path).convert("L").resize((256, 256), Image.NEAREST))
        prob_maps.append(prob)
        gt_masks.append(lbl > 128)

    print(f"  {len(prob_maps)} pairs loaded\n")

    header = f"{'Threshold':>10} {'IoU':>8} {'F1':>8} {'Precision':>10} {'Recall':>8}"
    print(header)
    print("-" * len(header))

    results = []
    for thr in THRESHOLDS:
        ious, f1s, precs, recs = [], [], [], []
        for prob, gt in zip(prob_maps, gt_masks):
            pred = prob >= thr
            m = compute_metrics_flat(pred, gt)
            ious.append(m["iou"])
            f1s.append(m["f1"])
            precs.append(m["precision"])
            recs.append(m["recall"])

        row = {
            "threshold": thr,
            "iou": round(float(np.mean(ious)), 4),
            "f1": round(float(np.mean(f1s)), 4),
            "precision": round(float(np.mean(precs)), 4),
            "recall": round(float(np.mean(recs)), 4),
        }
        results.append(row)
        print(
            f"{thr:>10.2f} {row['iou']:>8.4f} {row['f1']:>8.4f} "
            f"{row['precision']:>10.4f} {row['recall']:>8.4f}"
        )

    best = max(results, key=lambda r: r["f1"])
    print(f"\nRecommended threshold (max F1): {best['threshold']:.2f}")
    print(
        f"  IoU={best['iou']:.4f}  F1={best['f1']:.4f}  "
        f"P={best['precision']:.4f}  R={best['recall']:.4f}"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recommended_threshold": best["threshold"],
        "sweep": results,
        "checkpoint": str(checkpoint),
    }
    output.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved to {output}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        checkpoint=args.checkpoint,
        data_dir=args.data_dir,
        output=args.output,
    )
