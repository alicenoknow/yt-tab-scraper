"""tab-scraper: YouTube video with a guitar-tab strip overlay -> PDF of the strips in play order.

The pipeline core is the pure function `run(url, out_dir, ...) -> Result` below -
no CLI logic, so a web layer can wrap it later. One stage per module:
download.py (yt-dlp + ffmpeg) -> detect.py (find the tab region) ->
dedup.py (collapse identical consecutive frames) -> pdf.py (stack into A4 pages).
The algorithm is documented in ALGORITHM.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dedup import dedup, dhash
from .detect import detect_crop, save_crop_debug
from .download import download, extract_frames
from .errors import PipelineError
from .pdf import make_pdf

__all__ = ["run", "Result", "PipelineError", "download", "extract_frames",
           "detect_crop", "save_crop_debug", "dedup", "dhash", "make_pdf"]


@dataclass
class Result:
    pdf: Path
    crop_debug: Path
    strips_dir: Path
    crop: tuple[int, int, int, int]  # x, y, w, h
    n_strips: int


def run(url: str, out_dir: Path, fps: float = 1.0,
        crop: tuple[int, int, int, int] | None = None, threshold: float = 0.06,
        start: str | None = None, end: str | None = None) -> Result:
    out_dir = Path(out_dir)
    work = out_dir / "work"
    video = download(url, work)
    frames_dir = work / f"frames-{video.stem}-{fps}-{start or 0}-{end or 'end'}".replace(":", ".")
    frames = extract_frames(video, frames_dir, fps, start, end)
    if not frames:
        raise PipelineError("no frames extracted")

    crop = crop or detect_crop(frames)
    crop_debug = out_dir / "crop_debug.png"
    save_crop_debug(frames[len(frames) // 2], crop, crop_debug)

    strips = dedup(frames, crop, threshold)
    strips_dir = out_dir / "strips"
    strips_dir.mkdir(parents=True, exist_ok=True)
    for old in strips_dir.glob("*.png"):
        old.unlink()
    for i, s in enumerate(strips):
        s.save(strips_dir / f"{i:04d}.png")

    pdf = out_dir / "tab.pdf"
    make_pdf(strips, pdf)
    return Result(pdf=pdf, crop_debug=crop_debug, strips_dir=strips_dir,
                  crop=crop, n_strips=len(strips))
