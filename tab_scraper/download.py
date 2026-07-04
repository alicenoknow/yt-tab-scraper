"""Stage 1+2: yt-dlp download and ffmpeg frame extraction, both cached under work/."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from .errors import PipelineError


def download(url: str, dest: Path) -> Path:
    import yt_dlp

    dest.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:12]  # cache per URL, not per out dir
    existing = list(dest.glob(f"{key}.*"))
    if existing:  # cached from a previous run; delete work/ to force re-download
        return existing[0]
    opts = {
        # video-only stream is enough (no audio needed) and avoids an ffmpeg merge
        "format": "bestvideo[height<=1080]/best[height<=1080]/best",
        "outtmpl": str(dest / f"{key}.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise PipelineError(f"download failed: {e}") from None
    files = list(dest.glob(f"{key}.*"))
    if not files:
        raise PipelineError(f"download produced no video file - is this a valid video URL? {url}")
    return files[0]


def extract_frames(video: Path, frames_dir: Path, fps: float,
                   start: str | None = None, end: str | None = None) -> list[Path]:
    if not shutil.which("ffmpeg"):
        raise PipelineError("ffmpeg not found on PATH (brew install ffmpeg)")
    frames_dir.mkdir(parents=True, exist_ok=True)
    if not any(frames_dir.glob("f*.jpg")):  # cached; delete work/ to re-extract
        trim = (["-ss", start] if start else []) + (["-to", end] if end else [])
        subprocess.run(
            ["ffmpeg", *trim, "-i", str(video), "-vf", f"fps={fps}", "-qscale:v", "2",
             "-loglevel", "error", str(frames_dir / "f%06d.jpg")],
            check=True,
        )
    return sorted(frames_dir.glob("f*.jpg"))
