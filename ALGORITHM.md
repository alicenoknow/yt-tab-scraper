# The algorithm, mechanically

Pipeline (one module per stage):

```
url ──download.py──▶ work/<sha>.mp4 ──ffmpeg──▶ work/frames-*/f000001.jpg …
                                                        │
                                          detect.py: crop (x, y, w, h)
                                                        │
                                          dedup.py: strips (play order)
                                                        │
                                   pdf.py: tab.pdf  +  strips/*.png
```

## 1. Download (`download.py: download`)

- Cache key: `sha1(url)[:12]` → `work/<key>.mp4`. Skips download if file exists.
- Format: `bestvideo[height<=1080]/best[height<=1080]/best` — video-only to save bandwidth, 1080p cap since detection doesn't need 4K.
- Errors: `yt_dlp.utils.DownloadError` or empty glob after "success" → `PipelineError`.

## 2. Frame extraction (`download.py: extract_frames`)

```
ffmpeg [-ss START] [-to END] -i video -vf fps=FPS -qscale:v 2 frames/f%06d.jpg
```

- `-ss/-to` before `-i` = input seeking (jumps to keyframe, skips decoding).
- `fps=1` default — strips hold ~7–12 s, so 1 fps gives plenty of samples. Use `--fps 2` for faster-flipping videos.
- `-qscale:v 2` = high-quality JPEG; artifacts are below all detection thresholds.
- Cache dir encodes all params: `frames-<videokey>-<fps>-<start>-<end>` — any change → different dir.

## 3. Crop detection (`detect.py`)

Goal: find one rectangle `(x, y, w, h)` containing the tab across all frames.

### 3.1 Frame sampling

Sample 9 frames spread across the middle 70% (skip first/last 15% to avoid intros/outros).

### 3.2 Edge map

Convert to grayscale, compute vertical gradient `np.diff(axis=0)`, threshold at 25. Staff lines produce strong horizontal edges; threshold is low enough to catch anti-aliased gray lines.

### 3.3 Line rows

Keep rows where >30% of the width is an edge (`edge.mean(axis=1) > 0.3`). Staff lines span the strip width and score high; scenery edges rarely reach 0.3.

### 3.4 Clustering rows → line centers

Merge consecutive `line_rows` with gaps ≤ 3 px into clusters; take each cluster's mean as a line center.

### 3.5 Evenly spaced runs → the tab staff

Find the longest window of consecutive line centers (≥ 6 lines) with uniform spacing: `gaps.min() > 0.55*median` and `gaps.max() < 1.8*median`. This picks the 6-string tab staff while rejecting windows that straddle two staffs (huge gap) or hit irregular beam regions.

### 3.6 Notation staff extension

Any valid run (≥ 5 lines) sitting above the tab staff within `2.5 × tab-band-height` extends the band upward. No-op for tab-only videos.

### 3.7 Horizontal extent

Within the band's line rows, find columns where >50% of staff lines have an edge. First and last such column define `x0, x1`. Falls back to full width if <20% of columns qualify.

### 3.8 Merging bands across frames

- **Quorum:** need at least `max(2, samples//2)` detected bands, else `PipelineError`.
- **Outlier drop:** discard bands whose vertical center is >1.5 × median-height from the median center.
- **Union** of survivors: take `min(y0), max(y1), min(x0), max(x1)` since the staff drifts between re-renders.

### 3.9 White-panel snap

The band stops at outer staff lines but fret numbers and beams extend beyond. Use a cross-sample median of per-row whiteness (`pixel > 200` fraction) to find the panel edges:

- **Panel mode** (top rows have whitef > 0.6): walk top/bottom outward while rows stay >0.6 white. Capped at `0.7 × band-height`.
- **Overlay fallback**: fixed pad of `0.35 × band-height` each side.

Horizontal padding: `max(4, (x1-x0)//50)` px.

### 3.10 Debug overlay

`save_crop_debug` draws the rectangle on the middle frame → `crop_debug.png`. Always check — wrong detection still yields plausible-looking output.

## 4. Dedup (`dedup.py`)

Goal: collapse ~150 frames into ~15 unique strips, preserving play order and keeping legitimate repeats.

### 4.1 Difference hash

Resize crop to 33×8, compare each pixel to its left neighbor → 256-bit hash encoding horizontal structure. Immune to brightness/contrast flicker. Distance = fraction of differing bits.

Measured: same strip ≤ 0.04, different strips ≥ 0.15. Default threshold 0.06.

### 4.2 Core region

Hash only the central slab (middle half vertically, trimmed 5% each side horizontally) to exclude volatile padding edges. Full crop is still used for output.

### 4.3 Run building

Compare each frame to the **previous frame** (not the run's first). Same (distance ≤ threshold) → extend run; different → new run. Runs never merge across time, so repeats appear twice.

### 4.4 Representative frame

Each run contributes its middle frame (`run[len//2]`), avoiding transition frames at boundaries.

### 4.5 Tuning `--threshold`

| Symptom | Fix |
|---|---|
| Same strip appears twice adjacent | raise threshold (e.g. 0.10) |
| Two different strips merged | lower threshold (e.g. 0.03) |
| Strip missing entirely | use `--fps 2` |

## 5. PDF assembly (`pdf.py`)

- Page = A4 at 150 dpi (1240×1754 px). Margin 40 px, gap between strips 24 px.
- Each strip is resized to inner width (1160 px), height scaled proportionally.
- Strips are placed top-to-bottom; overflow starts a new page.
- Saved via Pillow's multi-page JPEG-in-PDF.

## 6. Cache invalidation

| Artifact | Invalidated by |
|---|---|
| `work/<sha>.mp4` | different URL string (or delete `work/`) |
| `work/frames-…/` | any extraction param change |
| `crop_debug.png`, `strips/`, `tab.pdf` | overwritten every run |

Detection and dedup always recompute (seconds); only network and ffmpeg work is cached.

## Constants reference

| Constant | Value | Why |
|---|---|---|
| edge threshold | 25 | catches anti-aliased gray lines |
| line-row width fraction | 0.30 | staff spans ≥ ~40% of frame; scenery stays below |
| cluster gap | ≤ 3 px | one line = 2–4 adjacent transition rows |
| gap uniformity | (0.55, 1.8)×median | tolerates jitter; rejects inter-staff jumps |
| min lines: tab / notation | 6 / 5 | guitar tab = 6 strings; notation = 5 lines |
| notation search range | 2.5 × band height | covers observed staff gaps with headroom |
| samples | 9 | robust medians; detection stays < 1 s |
| intro/outro trim | 15% each | skips typical title/outro cards |
| outlier drop | 1.5 × median height | rejects false positives far from real staff |
| white pixel / row threshold | > 200 / > 0.6 | separates panel rows from footage |
| walk cap | 0.7 × band height | prevents runaway on all-white frames |
| fallback pad | 0.35 × band height | covers fret numbers + beams in overlay mode |
| hash size | 32 × 8 | matches ~7:1 strip aspect; 256 bits |
| core inset | w/20, h/4 | excludes volatile padded edges |
| dedup threshold | 0.06 | sits between same (≤ 0.04) and different (≥ 0.15) |
| page, margin, gap | 1240×1754, 40, 24 | A4 @ 150 dpi |
