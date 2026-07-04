"""Stage 3: find the tab region - staff-line detection, band merging, white-panel snap.

Full mechanical walkthrough with worked examples: ALGORITHM.md (section 3).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .errors import PipelineError


def _find_band(gray: np.ndarray, edge_thresh: float) -> tuple[int, int, int, int] | None:
    """One frame: find >=6 long, evenly spaced horizontal lines -> (x0, x1, y0, y1)."""
    edge = np.abs(np.diff(gray, axis=0)) > edge_thresh
    width = edge.shape[1]
    line_rows = np.where(edge.mean(axis=1) > 0.3)[0]
    if len(line_rows) < 6:
        return None

    # merge adjacent edge rows (top+bottom of a thick line) into line centers
    clusters: list[list[int]] = []
    for r in line_rows:
        if clusters and r - clusters[-1][-1] <= 3:
            clusters[-1].append(int(r))
        else:
            clusters.append([int(r)])
    ys = [int(np.mean(c)) for c in clusters]

    # runs of consecutive centers with near-even spacing: >=6 lines = tab staff,
    # >=5 lines = possibly a notation staff; random gameplay edges qualify as neither
    # ponytail: a stray line inside the staff breaks the run; --crop is the fallback
    runs: list[tuple[int, int]] = []
    for i in range(len(ys)):
        for j in range(i + 4, len(ys)):
            gaps = np.diff(ys[i:j + 1])
            med = float(np.median(gaps))
            if med > 0 and gaps.min() > 0.55 * med and gaps.max() < 1.8 * med:
                runs.append((i, j))
    tab = max(((i, j) for i, j in runs if j - i >= 5),
              key=lambda r: (r[1] - r[0], -float(np.std(np.diff(ys[r[0]:r[1] + 1])))),
              default=None)
    if not tab:
        return None
    i, j = tab
    y0, y1 = ys[i], ys[j]

    # a 5-line notation staff sitting just above the tab staff belongs to the same
    # panel - extend the band to include it so the notes aren't cropped away
    above = [r for r in runs if ys[r[1]] < y0 and y0 - ys[r[1]] < 2.5 * (y1 - y0)]
    if above:
        y0 = min(ys[r[0]] for r in above)

    # x extent: columns the staff lines actually span
    lr = [r for r in line_rows if y0 - 2 <= r <= y1 + 2]
    cols = np.where(edge[lr].mean(axis=0) > 0.5)[0]
    x0, x1 = (int(cols[0]), int(cols[-1])) if len(cols) > 0.2 * width else (0, width - 1)
    return (x0, x1, y0, y1)


def detect_crop(frame_paths: list[Path], samples: int = 9,
                edge_thresh: float = 25.0) -> tuple[int, int, int, int]:
    """Detect the tab staff per sampled frame, then merge the bands: drop outliers vs
    the median (one-off gameplay artifacts), union the rest - the staff can shift a few
    dozen pixels between systems and the crop must cover every position."""
    n = len(frame_paths)
    lo, hi = int(n * 0.15), max(int(n * 0.15), n - 1 - int(n * 0.15))  # skip intro/outro
    idx = sorted(set(np.linspace(lo, hi, min(samples, n)).astype(int)))
    grays = [np.asarray(Image.open(frame_paths[i]).convert("L"), dtype=float) for i in idx]
    height, width = grays[0].shape

    bands = [b for b in (_find_band(g, edge_thresh) for g in grays) if b]
    if len(bands) < max(2, len(idx) // 2):
        raise PipelineError(
            f"tab strip found in only {len(bands)}/{len(idx)} sampled frames; "
            "pass --crop x,y,w,h (or --start/--end if tabs cover part of the video)")
    mid = float(np.median([(b[2] + b[3]) / 2 for b in bands]))
    h_med = float(np.median([b[3] - b[2] for b in bands]))
    good = [b for b in bands if abs((b[2] + b[3]) / 2 - mid) < 1.5 * h_med]
    x0 = min(b[0] for b in good)
    x1 = max(b[1] for b in good)
    y0 = min(b[2] for b in good)
    y1 = max(b[3] for b in good)

    # tabs/notes usually sit on a uniform white panel: extend the band while rows
    # stay mostly white (median across samples, so shifting beams/numbers don't
    # block the walk) and stop at the panel edge. Blind padding is only the
    # fallback for overlay strips without a white background.
    whitef = np.median(np.stack([(g[:, x0:x1 + 1] > 200).mean(axis=1) for g in grays]), axis=0)
    pad = max(4, int(0.35 * (y1 - y0)))  # tab numbers/chords stick out past the outer lines
    cap = int(0.7 * (y1 - y0))
    if whitef[y0:y0 + 5].mean() > 0.6:  # band sits on white -> panel video
        top = y0
        while top > max(0, y0 - cap) and whitef[top - 1] > 0.6:
            top -= 1
        bottom = y1
        while bottom < min(height, y1 + cap) - 1 and whitef[bottom + 1] > 0.6:
            bottom += 1
        bottom += 1
    else:  # overlay strip: no panel edge to snap to
        top = max(0, y0 - pad)
        bottom = min(height, y1 + pad)

    xpad = max(4, (x1 - x0) // 50)
    x = max(0, x0 - xpad)
    return (x, top, min(width, x1 + xpad) - x, bottom - top)


def save_crop_debug(frame_path: Path, crop: tuple[int, int, int, int], dest: Path) -> None:
    img = Image.open(frame_path).convert("RGB")
    x, y, w, h = crop
    ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=3)
    img.save(dest)
