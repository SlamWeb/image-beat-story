"""Make an optional alpha protection matte from user/agent-chosen ellipses.

Broad Gaussian-distance feather is an unapproved visual candidate, not a promise
of invisible moving seams. Inputs and existing rendered videos are never edited.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def create_mask(config: dict) -> np.ndarray:
    width, height = config.get("width"), config.get("height")
    if (not isinstance(width, int) or isinstance(width, bool) or width <= 0
            or not isinstance(height, int) or isinstance(height, bool) or height <= 0):
        raise ValueError("width and height must be positive integers")
    ellipses = config.get("ellipses")
    if not isinstance(ellipses, list) or not ellipses:
        raise ValueError("ellipses must be a nonempty list; choose subject/title regions for this input")
    y, x = np.mgrid[:height, :width].astype(np.float64)
    remaining = np.ones((height, width), np.float64)
    for index, ellipse in enumerate(ellipses):
        values = [ellipse.get(key) for key in ("cx", "cy", "rx", "ry", "feather")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError(f"ellipse {index}: require finite cx, cy, rx, ry, feather")
        cx, cy, rx, ry, feather = values
        if min(rx, ry, feather) <= 0:
            raise ValueError(f"ellipse {index}: rx, ry, feather must be positive")
        dx, dy = x - cx, y - cy
        radius = np.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
        # Pixel distance measured outward along the ray from the ellipse center.
        # Not a true shortest Euclidean distance; feather is consistently in px.
        ray_boundary = np.divide(np.hypot(dx, dy), radius, out=np.zeros_like(radius), where=radius > 0)
        outside_pixels = np.maximum(radius - 1, 0) * ray_boundary
        field = np.exp(-0.5 * (outside_pixels / feather) ** 2)
        remaining *= 1 - field
    return 1 - remaining


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="RGBA PNG, white RGB with protection in alpha")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".png":
        parser.error("--output must end in .png")
    if args.output.exists() and not args.overwrite:
        parser.error("output exists; choose a new version or explicitly pass --overwrite")
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    alpha = create_mask(config)
    rgba = np.full((*alpha.shape, 4), 255, np.uint8)
    rgba[:, :, 3] = np.rint(alpha * 255).astype(np.uint8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(args.output)
    report = {
        "output": str(args.output.resolve()), "width": config["width"], "height": config["height"],
        "method": "plateau + Gaussian radial-distance tail + soft union; no finite outer rim",
        "featherDefinition": "pixels along a center-to-boundary ray; one sigma outside inner ellipse",
        "ellipses": config["ellipses"],
        "maxAdjacentAlphaDelta": max(float(np.abs(np.diff(alpha, axis=axis)).max(initial=0)) for axis in (0, 1)),
        "visualStatus": "candidate_requires_full_resolution_still_and_temporal_review",
        "previousVideosModified": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
