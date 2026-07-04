"""Stage 5: stack the strips onto A4 pages, play order preserved."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def make_pdf(strips: list[Image.Image], dest: Path,
             page: tuple[int, int] = (1240, 1754), margin: int = 40, gap: int = 24) -> None:
    pw, ph = page  # A4 @ 150dpi
    inner = pw - 2 * margin
    pages: list[Image.Image] = []
    cy = ph
    for s in strips:
        s = s.resize((inner, max(1, round(s.height * inner / s.width))))
        if cy + s.height > ph - margin:
            pages.append(Image.new("RGB", page, "white"))
            cy = margin
        pages[-1].paste(s, (margin, cy))
        cy += s.height + gap
    pages[0].save(dest, save_all=True, append_images=pages[1:], resolution=150)
