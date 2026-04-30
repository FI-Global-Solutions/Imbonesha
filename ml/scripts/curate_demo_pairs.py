"""Curate LEVIR-CD test pairs for the RHA demo.

Runs inference on all (or the first --max-pairs) test pairs, measures per-pair
predicted IoU against the ground truth mask, and saves side-by-side PNGs so you
can manually pick the 3-5 best-looking pairs to use in seed_levir_demo_scenes.

Output:
  ml/eval_outputs/curation/{pair_id}_{iou:.2f}.png   — side-by-side: T1|T2|GT|Pred|Overlay
  ml/eval_outputs/curation/ranked_pairs.json         — list of {pair_id, iou} sorted desc

Usage (on host, requires the session 4 venv or pip install torch rasterio shapely pillow):
  python ml/scripts/curate_demo_pairs.py \
      --data-dir ml/data/LEVIR-CD \
      --checkpoint ml/checkpoints/siamese_unet_v2.pth \
      --output-dir ml/eval_outputs/curation \
      --max-pairs 50

Usage (inside ml-service container):
  docker compose -f infra/docker-compose.yml exec ml-service \
      python -m scripts.curate_demo_pairs \
          --data-dir /app/data/LEVIR-CD \
          --checkpoint /app/checkpoints/siamese_unet_v2.pth \
          --output-dir /app/eval_outputs/curation \
          --max-pairs 50
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IMG_SIZE = 256


def _load_img(path: Path) -> np.ndarray:
    from PIL import Image
    img = Image.open(path).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    return np.array(img, dtype=np.float32) / 255.0


def _load_mask(path: Path) -> np.ndarray:
    from PIL import Image
    img = Image.open(path).convert("L").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)
    return (np.array(img, dtype=np.float32) > 128).astype(np.float32)


def _to_tensor(arr: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).float()


def _iou(pred_bin: np.ndarray, gt: np.ndarray) -> float:
    inter = (pred_bin * gt).sum()
    union = (pred_bin + gt - pred_bin * gt).sum()
    return float(inter / (union + 1e-6))


def _save_panel(
    t1: np.ndarray,
    t2: np.ndarray,
    gt: np.ndarray,
    pred_prob: np.ndarray,
    pred_bin: np.ndarray,
    iou: float,
    out_path: Path,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    def arr_to_img(a: np.ndarray) -> Image.Image:
        if a.ndim == 2:
            rgb = np.stack([a, a, a], axis=-1)
        else:
            rgb = a
        return Image.fromarray((rgb * 255).astype(np.uint8))

    # Overlay: T2 with red predicted-change pixels.
    overlay = t2.copy()
    overlay[pred_bin > 0] = [1.0, 0.0, 0.0]

    panels = [
        ("T1 (before)", arr_to_img(t1)),
        ("T2 (after)", arr_to_img(t2)),
        ("Ground truth", arr_to_img(gt)),
        ("Predicted prob", arr_to_img(pred_prob)),
        (f"Overlay (IoU={iou:.2f})", arr_to_img(overlay)),
    ]

    pad = 4
    label_h = 18
    cell_w = IMG_SIZE + pad
    cell_h = IMG_SIZE + label_h + pad
    total_w = cell_w * len(panels)
    canvas = Image.new("RGB", (total_w, cell_h), color=(30, 30, 30))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except Exception:
        font = ImageFont.load_default()

    for i, (label, img) in enumerate(panels):
        x = i * cell_w + pad // 2
        canvas.paste(img, (x, label_h))
        draw = ImageDraw.Draw(canvas)
        draw.text((x, 2), label, fill=(220, 220, 220), font=font)

    canvas.save(out_path)


def curate(
    data_dir: Path,
    checkpoint: Path,
    output_dir: Path,
    max_pairs: int,
    threshold: float,
    device_str: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Import inference — works on host (ml.app) or in container (app).
    try:
        from ml.app.inference import SiameseUNet, _pick_device
    except ModuleNotFoundError:
        from app.inference import SiameseUNet, _pick_device  # type: ignore[no-redef]

    device = torch.device(device_str or _pick_device())
    model = SiameseUNet(base_ch=32).to(device)

    if checkpoint.exists():
        state = torch.load(checkpoint, map_location=device, weights_only=True)
        if isinstance(state, dict) and "model" in state:
            state = state["model"]
        model.load_state_dict(state)
        logger.info("Loaded checkpoint %s on %s", checkpoint, device)
    else:
        logger.warning("Checkpoint not found at %s — using random weights", checkpoint)

    model.eval()

    a_dir = data_dir / "A"
    b_dir = data_dir / "B"
    lbl_dir = data_dir / "label"

    test_names = sorted(
        p.stem for p in a_dir.iterdir()
        if p.suffix.lower() in (".png", ".jpg", ".tif") and p.stem.startswith("test")
    )[:max_pairs]
    logger.info("Evaluating %d test pairs", len(test_names))

    rankings: list[dict] = []

    for name in test_names:
        a_path = next((a_dir / f"{name}{s}" for s in (".png", ".jpg", ".tif") if (a_dir / f"{name}{s}").exists()), None)
        b_path = next((b_dir / f"{name}{s}" for s in (".png", ".jpg", ".tif") if (b_dir / f"{name}{s}").exists()), None)
        lbl_path = next((lbl_dir / f"{name}{s}" for s in (".png", ".jpg", ".tif") if (lbl_dir / f"{name}{s}").exists()), None)

        if not (a_path and b_path and lbl_path):
            logger.warning("Missing files for %s — skipping", name)
            continue

        t1 = _load_img(a_path)
        t2 = _load_img(b_path)
        gt = _load_mask(lbl_path)

        with torch.no_grad():
            logits = model(_to_tensor(t1).to(device), _to_tensor(t2).to(device))
            prob = torch.sigmoid(logits).squeeze().cpu().numpy()

        pred_bin = (prob >= threshold).astype(np.float32)
        pair_iou = _iou(pred_bin, gt)

        panel_path = output_dir / f"{name}_{pair_iou:.2f}.png"
        _save_panel(t1, t2, gt, prob, pred_bin, pair_iou, panel_path)

        rankings.append({"pair_id": name, "iou": round(pair_iou, 4)})
        logger.info("%s  iou=%.4f  → %s", name, pair_iou, panel_path.name)

    rankings.sort(key=lambda r: r["iou"], reverse=True)

    ranked_path = output_dir / "ranked_pairs.json"
    ranked_path.write_text(json.dumps(rankings, indent=2))

    logger.info("Done. Top 5:")
    for r in rankings[:5]:
        logger.info("  %s  iou=%.4f", r["pair_id"], r["iou"])
    logger.info("Full ranking → %s", ranked_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Curate LEVIR-CD test pairs for demo")
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, default=Path("ml/checkpoints/siamese_unet_v2.pth"))
    p.add_argument("--output-dir", type=Path, default=Path("ml/eval_outputs/curation"))
    p.add_argument("--max-pairs", type=int, default=128)
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--device", type=str, default="")
    return p.parse_args()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    args = parse_args()
    curate(
        data_dir=args.data_dir,
        checkpoint=args.checkpoint,
        output_dir=args.output_dir,
        max_pairs=args.max_pairs,
        threshold=args.threshold,
        device_str=args.device,
    )
