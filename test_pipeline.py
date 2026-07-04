"""Self-check on synthetic frames: fake gameplay + a 6-line tab strip that swaps
content A(x3) -> B(x3) -> A(x2). Expects crop over the strip and 3 strips (repeat kept).

Run: .venv/bin/python test_pipeline.py
"""

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from tab_scraper import dedup, detect_crop, dhash, make_pdf

STRIP = (40, 240, 600, 320)  # x0, y0, x1, y1


def make_frame(path: Path, content_seed: int, frame_seed: int) -> None:
    img = Image.new("RGB", (640, 360), (30, 60, 90))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(frame_seed)  # "gameplay": circles that move every frame
    for _ in range(20):
        cx, cy = int(rng.integers(0, 640)), int(rng.integers(0, 360))
        d.ellipse([cx, cy, cx + 30, cy + 30], fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    x0, y0, x1, y1 = STRIP
    d.rectangle([x0, y0, x1, y1], fill="white")
    for i in range(6):
        y = y0 + 10 + i * 12
        d.line([x0 + 10, y, x1 - 10, y], fill=(60, 60, 60), width=1)
    rng = np.random.default_rng(content_seed)  # "notes": deterministic per content
    for _ in range(12):
        x = int(rng.integers(x0 + 20, x1 - 30))
        y = y0 + 10 + int(rng.integers(0, 6)) * 12 - 3
        d.rectangle([x, y, x + 6, y + 6], fill="black")
    img.save(path, quality=90)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        contents = [1, 1, 1, 2, 2, 2, 1, 1]  # A A A B B B A A
        paths = []
        for i, c in enumerate(contents):
            p = tmp / f"f{i:06d}.jpg"
            make_frame(p, content_seed=c, frame_seed=100 + i)
            paths.append(p)

        crop = detect_crop(paths, samples=len(paths))
        x, y, w, h = crop
        sx0, sy0, sx1, sy1 = STRIP
        assert y <= sy0 + 15 and y + h >= sy1 - 15, f"crop misses strip vertically: {crop}"
        assert x <= sx0 + 15 and x + w >= sx1 - 15, f"crop misses strip horizontally: {crop}"
        assert h < 200, f"crop way too tall: {crop}"

        strips = dedup(paths, crop, threshold=0.06)
        assert len(strips) == 3, f"expected 3 strips (A B A), got {len(strips)}"
        def core(img):  # same central region dedup hashes (pad edges contain gameplay)
            w, h = img.size
            return img.crop((w // 20, h // 4, w - w // 20, h - h // 4))

        d02 = (dhash(core(strips[0])) ^ dhash(core(strips[2]))).mean()
        d01 = (dhash(core(strips[0])) ^ dhash(core(strips[1]))).mean()
        assert d02 <= 0.06 < d01, f"repeat A~A ({d02:.3f}) vs A!=B ({d01:.3f})"

        pdf = tmp / "tab.pdf"
        make_pdf(strips, pdf)
        assert pdf.stat().st_size > 1000, "pdf too small"

    print("ok: crop detected, A B A -> 3 strips, repeat kept, pdf written")


if __name__ == "__main__":
    main()
