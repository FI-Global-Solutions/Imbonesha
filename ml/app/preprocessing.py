"""Preprocessing utilities for change detection inference.

Applies radiometric normalization (histogram matching) and simple
cloud/shadow masking before feeding image pairs to the model.

AROSICS co-registration is listed as a dependency in the design doc but
requires the full AROSICS package (heavy C++ deps). For the stub pipeline
we skip it — in production, register T2 to T1 before calling this module.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def load_image_as_array(path: str | Path) -> np.ndarray:
    """Load a GeoTIFF (or PNG/JPG for tests) as a float32 HWC array in [0, 1].

    Handles both rasterio (GeoTIFF) and PIL (PNG/JPEG) backends so tests
    can use synthetic images without a full rasterio install.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".tif", ".tiff", ".cog"):
        return _load_rasterio(path)
    return _load_pil(path)


def _load_rasterio(path: Path) -> np.ndarray:
    try:
        import rasterio  # type: ignore
    except ImportError:
        logger.warning("rasterio not available — falling back to PIL for %s", path)
        return _load_pil(path)

    with rasterio.open(path) as src:
        # Read up to 3 bands (RGB). Many satellite scenes have more.
        n_bands = min(src.count, 3)
        data = src.read(list(range(1, n_bands + 1)))  # shape: (C, H, W)
        # Normalise to [0, 1] using the dtype range.
        if np.issubdtype(data.dtype, np.integer):
            info = np.iinfo(data.dtype)
            arr = data.astype(np.float32) / info.max
        else:
            arr = data.astype(np.float32)

    return np.transpose(arr, (1, 2, 0))  # HWC


def _load_pil(path: Path) -> np.ndarray:
    from PIL import Image  # type: ignore

    img = Image.open(path).convert("RGB")
    return np.array(img, dtype=np.float32) / 255.0


def histogram_match(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Match the histogram of *source* to *reference* channel-wise.

    Both arrays should be float32 HWC in [0, 1].  Returns a float32 HWC
    array clipped to [0, 1].

    This is a simple percentile-based stretch — sufficient for demo
    purposes.  Production should use a proper CDF histogram match.
    """
    assert source.shape == reference.shape, (
        f"Shape mismatch: {source.shape} vs {reference.shape}"
    )
    out = np.empty_like(source)
    for c in range(source.shape[2]):
        s = source[:, :, c]
        r = reference[:, :, c]
        # Fit a linear mapping from source's mean/std to reference's.
        s_mean, s_std = s.mean(), s.std() + 1e-8
        r_mean, r_std = r.mean(), r.std() + 1e-8
        out[:, :, c] = (s - s_mean) * (r_std / s_std) + r_mean
    return np.clip(out, 0.0, 1.0)


def cloud_shadow_mask(image: np.ndarray, brightness_threshold: float = 0.85) -> np.ndarray:
    """Return a boolean mask: True where pixels are likely cloud or shadow.

    Uses a simple brightness heuristic:
    - Bright (mean > threshold) → cloud
    - Very dark (mean < 1 - threshold) → shadow

    In production this should be replaced with s2cloudless or a dedicated
    cloud-detection model.

    Args:
        image: float32 HWC in [0, 1].
        brightness_threshold: Pixels with mean brightness above this are
            considered cloud, below (1 - threshold) are shadow.

    Returns:
        bool HW mask — True means masked out (invalid).
    """
    mean_brightness = image.mean(axis=2)  # H×W
    cloud = mean_brightness > brightness_threshold
    shadow = mean_brightness < (1.0 - brightness_threshold)
    return cloud | shadow


def prepare_pair(
    t1_path: str | Path,
    t2_path: str | Path,
    target_size: tuple[int, int] = (256, 256),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load, normalise, and optionally resize an image pair.

    Returns:
        t1_arr, t2_arr: float32 HWC arrays in [0, 1], same shape.
        cloud_mask: bool HW mask (True = invalid) based on T2.
    """
    t1 = load_image_as_array(t1_path)
    t2 = load_image_as_array(t2_path)

    # Resize to model input size if needed.
    if t1.shape[:2] != target_size:
        t1 = _resize(t1, target_size)
    if t2.shape[:2] != target_size:
        t2 = _resize(t2, target_size)

    # Histogram-match T2 to T1 to reduce radiometric differences.
    t2 = histogram_match(t2, t1)

    mask = cloud_shadow_mask(t2)
    return t1, t2, mask


def _resize(arr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    from PIL import Image

    h, w = size
    img = Image.fromarray((arr * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    return np.array(img, dtype=np.float32) / 255.0
