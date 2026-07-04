"""CLI wrapper around the pure pipeline core in __init__.run()."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import PipelineError, run


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="YouTube tab-overlay video -> PDF of tab strips")
    ap.add_argument("url", help="YouTube URL")
    ap.add_argument("-o", "--out", default="out", help="output directory (default: out)")
    ap.add_argument("--fps", type=float, default=1.0, help="frame sampling rate (default: 1)")
    ap.add_argument("--start", help="only scan from this time, e.g. 90 or 1:30")
    ap.add_argument("--end", help="only scan up to this time, e.g. 240 or 4:00")
    ap.add_argument("--crop", help="manual crop x,y,w,h (skips auto-detect)")
    ap.add_argument("--threshold", type=float, default=0.06,
                    help="dedup: max fraction of hash bits differing to count as the same strip")
    a = ap.parse_args(argv)
    # zsh tab-completion escapes ? and = ; inside quotes the backslashes survive
    # and yt-dlp then can't recognize the URL - strip them
    url = a.url.replace("\\", "")

    crop = None
    if a.crop:
        parts = a.crop.split(",")
        if len(parts) != 4:
            ap.error("--crop needs x,y,w,h")
        crop = tuple(int(v) for v in parts)

    try:
        r = run(url, Path(a.out), fps=a.fps, crop=crop, threshold=a.threshold,
                start=a.start, end=a.end)
    except PipelineError as e:
        sys.exit(f"error: {e}")
    print(f"{r.n_strips} strips -> {r.pdf}")
    print(f"verify the detected region: {r.crop_debug} (crop={','.join(map(str, r.crop))})")
    print(f"kept strips (for threshold tuning): {r.strips_dir}/")


if __name__ == "__main__":
    main()
