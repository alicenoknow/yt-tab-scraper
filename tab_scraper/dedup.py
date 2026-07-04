"""Stage 4: collapse consecutive frames showing the same strip (perceptual hashing).

Full mechanical walkthrough with worked examples: ALGORITHM.md (section 4).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def dhash(img: Image.Image, size: tuple[int, int] = (32, 8)) -> np.ndarray:
    w, h = size  # wide hash: strips are wide, the differing content is the numbers
    g = np.asarray(img.convert("L").resize((w + 1, h)), dtype=float)
    return g[:, 1:] > g[:, :-1]


def dedup(frame_paths: list[Path], crop: tuple[int, int, int, int],
          threshold: float) -> list[Image.Image]:
    """Collapse consecutive frames showing the same strip; keep play order and repeats."""
    x, y, w, h = crop
    box = (x, y, x + w, y + h)
    # hash only the central core: the crop is padded past the staff lines, and gameplay
    # bleeding into those edges would make every frame hash as unique
    core = (x + w // 20, y + h // 4, x + w - w // 20, y + h - h // 4)
    runs: list[list[Path]] = []
    prev = None
    for p in frame_paths:
        cur = dhash(Image.open(p).crop(core))
        # column-wise median: a playback cursor (narrow vertical band) flips bits
        # in 2-3 columns out of 32; median ignores those outliers
        if prev is not None and float(np.median((cur ^ prev).mean(axis=0))) <= threshold:
            runs[-1].append(p)
        else:
            runs.append([p])
        prev = cur
    # middle frame of each run: avoids grabbing a mid-swap frame at a run boundary
    return [Image.open(run[len(run) // 2]).crop(box) for run in runs]
