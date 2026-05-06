"""Change detection inference.

ChangeDetector loads a Siamese U-Net checkpoint and produces change
polygons from a pair of co-registered, normalised images.

Pipeline:
  1. Load T1 and T2 as float32 tensors.
  2. Forward pass → per-pixel change probability map.
  3. Threshold → binary mask.
  4. Vectorise with rasterio.features.shapes → GeoJSON-ish polygons.
  5. Filter by area (min 50 sqm, max 10 000 sqm).
  6. Return list of dicts with polygon + confidence.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from .config import settings
from .preprocessing import prepare_pair

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model definition — lightweight Siamese U-Net
# ---------------------------------------------------------------------------


def _conv_block(in_ch: int, out_ch: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class SiameseUNet(nn.Module):
    """Compact Siamese U-Net for binary change detection.

    Encoder processes T1 and T2 with shared weights; difference features
    are fed into a lightweight decoder that predicts a per-pixel change
    probability.

    Input:  two (B, 3, H, W) tensors, values in [0, 1].
    Output: (B, 1, H, W) change probability logits (before sigmoid).

    Args:
        base_ch: Base channel count (32 → ~1.2M parameters).
        dropout: Dropout rate applied after each decoder block (0 = disabled).
                 Use 0.3 during training to reduce overfitting.
    """

    def __init__(self, base_ch: int = 32, dropout: float = 0.0) -> None:
        super().__init__()

        # Shared encoder (weights tied via the same module reference).
        self.enc1 = _conv_block(3, base_ch)
        self.enc2 = _conv_block(base_ch, base_ch * 2)
        self.enc3 = _conv_block(base_ch * 2, base_ch * 4)

        self.pool = nn.MaxPool2d(2)

        # Bottleneck operates on concatenated difference features.
        self.bottleneck = _conv_block(base_ch * 4, base_ch * 4)

        # Decoder with optional dropout after each block.
        self.up2 = nn.ConvTranspose2d(base_ch * 4, base_ch * 2, 2, stride=2)
        self.dec2 = _conv_block(base_ch * 4, base_ch * 2)  # + skip diff
        self.drop2 = nn.Dropout2d(dropout) if dropout > 0 else nn.Identity()

        self.up1 = nn.ConvTranspose2d(base_ch * 2, base_ch, 2, stride=2)
        self.dec1 = _conv_block(base_ch * 2, base_ch)      # + skip diff
        self.drop1 = nn.Dropout2d(dropout) if dropout > 0 else nn.Identity()

        self.head = nn.Conv2d(base_ch, 1, 1)

    def _encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        return e1, e2, e3

    def forward(self, t1: torch.Tensor, t2: torch.Tensor) -> torch.Tensor:
        t1_e1, t1_e2, t1_e3 = self._encode(t1)
        t2_e1, t2_e2, t2_e3 = self._encode(t2)

        # Absolute difference at each scale — captures change magnitude.
        diff3 = torch.abs(t1_e3 - t2_e3)
        diff2 = torch.abs(t1_e2 - t2_e2)
        diff1 = torch.abs(t1_e1 - t2_e1)

        # diff3 is at 1/4 spatial resolution (after two pool ops in the encoder).
        # Pass through bottleneck in place — no extra pooling needed.
        b = self.bottleneck(diff3)

        # up2: 1/4 → 1/2, concat with diff2 (also 1/2)
        d2 = self.drop2(self.dec2(torch.cat([self.up2(b), diff2], dim=1)))
        # up1: 1/2 → 1/1, concat with diff1 (also 1/1)
        d1 = self.drop1(self.dec1(torch.cat([self.up1(d2), diff1], dim=1)))

        return self.head(d1)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ChangeDetector:
    """Loads a checkpoint and runs change detection inference."""

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        threshold: float | None = None,
        device: str | None = None,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path or settings.checkpoint_path)
        self.threshold = threshold or settings.detection_threshold
        self.device = torch.device(device or _pick_device())

        self.model = SiameseUNet(base_ch=32).to(self.device)
        self._loaded = False
        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        if not self.checkpoint_path.exists():
            logger.warning(
                "Checkpoint not found at %s — model will run with random weights. "
                "Run ml/scripts/train.py to create a checkpoint.",
                self.checkpoint_path,
            )
            self.model.eval()
            self._loaded = False
            return

        state = torch.load(self.checkpoint_path, map_location=self.device, weights_only=True)
        # Support both plain state_dict and {"model": state_dict} format.
        if isinstance(state, dict) and "model" in state:
            state = state["model"]
        self.model.load_state_dict(state)
        self.model.eval()
        self._loaded = True
        logger.info("Checkpoint loaded from %s on %s", self.checkpoint_path, self.device)

    @property
    def checkpoint_loaded(self) -> bool:
        return self._loaded

    def predict_mask(self, t1_path: str | Path, t2_path: str | Path) -> np.ndarray:
        """Return raw change probability map (H, W) with values in [0, 1].

        Same preprocessing as detect() but returns the sigmoid output before
        thresholding. Useful for threshold tuning and evaluation.
        """
        t1_arr, t2_arr, cloud_mask = prepare_pair(t1_path, t2_path)
        prob_map = self._predict(t1_arr, t2_arr)
        prob_map[cloud_mask] = 0.0
        return prob_map

    def detect(
        self,
        t1_path: str | Path,
        t2_path: str | Path,
    ) -> list[dict[str, Any]]:
        """Run change detection on an image pair.

        Args:
            t1_path: Path to the baseline (T1) image.
            t2_path: Path to the current (T2) image.

        Returns:
            List of polygon dicts, each with keys:
              - ``polygon``: list of [col, row] in *original image pixel space*
                (not inference-grid space — already scaled back up).
              - ``confidence``: Mean model probability within the polygon.
              - ``area_sqm``: Estimated area in square metres.
        """
        # Read original dimensions before prepare_pair resizes the image.
        orig_h, orig_w = _read_image_size(t1_path)

        t1_arr, t2_arr, cloud_mask = prepare_pair(t1_path, t2_path)

        # prepare_pair resizes to (256, 256) by default.
        inf_h, inf_w = t1_arr.shape[:2]

        prob_map = self._predict(t1_arr, t2_arr)

        # Zero out cloudy/shadowed areas so they don't generate false positives.
        prob_map[cloud_mask] = 0.0

        binary_mask = (prob_map >= self.threshold).astype(np.uint8)

        # Scale factors to convert inference-grid pixels → original-image pixels.
        scale_x = orig_w / inf_w
        scale_y = orig_h / inf_h

        polygons = self._vectorise(binary_mask, prob_map, scale_x=scale_x, scale_y=scale_y)
        return polygons

    def _predict(self, t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
        """Run model forward pass and return a float32 H×W probability map."""
        t1_t = _hwc_to_bchw(t1).to(self.device)
        t2_t = _hwc_to_bchw(t2).to(self.device)

        with torch.no_grad():
            logits = self.model(t1_t, t2_t)  # (1, 1, H, W)
            prob = torch.sigmoid(logits).squeeze().cpu().numpy()  # H×W

        return prob.astype(np.float32)

    def _vectorise(
        self,
        binary_mask: np.ndarray,
        prob_map: np.ndarray,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Convert a binary mask to filtered polygon dicts.

        Polygon coordinates are returned in *original image pixel space*:
        each (col, row) is multiplied by (scale_x, scale_y) before being
        added to the result, so the caller can apply the geo-transform of
        the full-resolution image directly.

        Area filtering is also performed in original-image pixel space so
        that min/max_polygon_sqm thresholds remain consistent regardless of
        inference resolution.
        """
        try:
            from rasterio.features import shapes as rio_shapes  # type: ignore
            from shapely.geometry import shape as shapely_shape  # type: ignore
        except ImportError:
            logger.error("rasterio / shapely required for polygonization")
            return []

        results = []
        h, w = binary_mask.shape
        # pixel_size_m in original-image space (2 m/px default at full res).
        pixel_size_m = 2.0
        # After scaling, each pixel in the inference grid represents
        # (scale_x * scale_y) original pixels.
        orig_px_per_inf_px = scale_x * scale_y
        sqm_per_inf_px = (pixel_size_m ** 2) * orig_px_per_inf_px

        for geom, val in rio_shapes(binary_mask, mask=binary_mask):
            if int(val) != 1:
                continue

            poly = shapely_shape(geom)
            area_sqm = poly.area * sqm_per_inf_px

            if area_sqm < settings.min_polygon_sqm:
                continue
            if area_sqm > settings.max_polygon_sqm:
                continue

            # Mean confidence within the polygon bounding box (fast approx).
            minx, miny, maxx, maxy = (int(v) for v in poly.bounds)
            minx = max(0, minx)
            miny = max(0, miny)
            maxx = min(w, maxx)
            maxy = min(h, maxy)
            roi = prob_map[miny:maxy, minx:maxx]
            confidence = float(roi.mean()) if roi.size > 0 else float(self.threshold)

            # Scale coords from inference-grid space → original-image pixel space.
            scaled_coords = [
                [col * scale_x, row * scale_y]
                for col, row in poly.exterior.coords
            ]

            results.append({
                "polygon": scaled_coords,
                "confidence": round(confidence, 4),
                "area_sqm": round(area_sqm, 1),
            })

        logger.info("Vectorised %d polygons (threshold=%.2f)", len(results), self.threshold)
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_image_size(path: str | Path) -> tuple[int, int]:
    """Return (height, width) of an image without loading all pixel data.

    Tries rasterio first (GeoTIFF), falls back to PIL.  Returns (256, 256)
    on any error so the scale factor defaults to 1.0 and behaviour is
    unchanged for synthetic test images that are already 256×256.
    """
    path = Path(path)
    try:
        import rasterio  # type: ignore
        with rasterio.open(path) as src:
            return src.height, src.width
    except Exception:
        pass
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            w, h = img.size
            return h, w
    except Exception:
        logger.warning("Could not read image size from %s — assuming 256×256", path)
        return 256, 256


def _pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    # Apple Silicon MPS — only if the build supports it.
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _hwc_to_bchw(arr: np.ndarray) -> torch.Tensor:
    """Convert float32 HWC numpy array to (1, C, H, W) tensor."""
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)  # 1,C,H,W
    return t.float()
