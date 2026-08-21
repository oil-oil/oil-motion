# Runtime Selection and Interaction Mapping

## Run Auto-Selection First

Run `motion_budget.py` first and implement the track returned by `delivery.selected`. The format is decided automatically by the Agent — do not ask the user.

| Selection | When used | Where Alpha is generated | Main advantage |
|---|---|---|---|
| `alpha-atlas` | small, circular, 2D, or high-frequency random access | offline keying at build time | stable response to arbitrary frame jumps |
| `chroma-video` | one-dimensional sequential, long timeline, large size, or atlas over budget | WebGL keying at runtime | high compression, avoids huge RGBA decode memory |

Both tracks share the same green-screen master, and the page background is always provided by the page layer. The video track is not a video with background baked in, and it cannot fall back to `<video autoplay>`.

A small atlas file does not mean small decode memory. RGBA decode memory is roughly `width × height × 4`. A 3840×3600 atlas needs about 52.7 MiB, so budgeting must use the real display size and target device.

## Atlas Constraints

- Uniform cell size.
- All frames share the same subject anchor.
- Cell width/height is at least final CSS width/height times target DPR; relying on the browser to upscale low-resolution frames is forbidden.
- Default single-atlas dimensions are at most 4096×4096; beyond that, let auto-selection switch to video. 2D parameters cannot be cut into a linear video — lower sampling or split states and re-budget.
- Use a manifest to store frame count, columns, rows, cell size, still frame, and parameter mapping.
- CSS `background-size` is `columns × 100%` and `rows × 100%`.
- Switching frames only updates `background-position`; do not create multiple transparent image layers.

Run the resource budget check first:

```bash
python3 scripts/motion_budget.py \
  --frames 180 --display 240x240 --dpr 2 --max-texture 4096 \
  --driver pointer --parameter-space circular \
  --report build/motion-budget.json --strict
```

Package the atlas only when it returns `alpha-atlas` and the budget passes; do not shrink cells to force everything into one atlas.

```css
.motion-sprite {
  width: 240px;
  aspect-ratio: 1;
  background-image: url("./motion.webp");
  background-repeat: no-repeat;
  background-size: 1600% 1500%;
  will-change: background-position;
}
```

## Green-Screen Video Constraints

- Use only for one-dimensional time parameters; prefer `linear` sequential access. Circular or one-dimensional random access uses video only when the atlas is over budget, and must add seek-latency acceptance; 2D input never uses video.
- Runtime material keeps a uniform green screen and is drawn as a transparent Canvas via `chroma-video-renderer.ts`.
- Use an all-keyframe MP4 so integer-frame `currentTime` seeks have stable forward and reverse latency.
- Video dimensions cover at least the max actual CSS size times target DPR, while not exceeding master resolution.
- Page background, text, and other visual layers live outside the Canvas; the video encoding must not include them.
- On WebGL or video failure, fall back to the static Alpha first frame; never show the raw green screen.

Full compile and acceptance rules are in [chroma-video.en.md](chroma-video.en.md).

## One-Dimensional Time Parameter

```text
progress = clamp((scrollY - start) / (end - start), 0, 1)
targetFrame = progress * (frameCount - 1)
```

The scroll listener only records the target value; updates happen in `requestAnimationFrame`. Recompute start/end positions when page layout changes.

## Circular Direction Parameter

```text
angle = atan2(pointerY - anchorY, pointerX - anchorX)
normalized = mod(angle - startAngle, 2π) / 2π
targetFrame = normalized * frameCount
```

When the current frame tracks the target frame, use the shortest circular distance:

```text
delta = wrap(target) - wrap(current)
if delta > frameCount / 2: delta -= frameCount
if delta < -frameCount / 2: delta += frameCount
```

Loop material must be checked for the last-frame-to-first-frame connection. If the generated video itself is not a loop, do not force wrap at runtime.

## 2D Parameter

Discrete index for a 2D grid:

```text
column = round(clamp(x, 0, 1) * (columns - 1))
row = round(clamp(y, 0, 1) * (rows - 1))
frame = row * columns + column
```

2D input defaults to nearest-neighbor frame selection with input damping to reduce jitter. Do not transparently overlap adjacent images, to avoid ghosting.

## Damping and Velocity

`lerp` tends to feel sticky under frame-rate variation and frequent reversals. Prefer `smoothDamp` with a velocity state and max speed:

- `smoothTime` controls tracking delay.
- `maxSpeed` limits unnatural fast twitching.
- Keep the velocity state across every reversal to avoid mechanical pauses.
- Cap `deltaTime` to avoid huge frame jumps when the tab is restored.

Start from the following ranges, then adjust by motion scale:

```text
smoothTime: 0.08–0.16 s
maxSpeed: 1.5–2.5× the total frame count per second
deltaTime cap: 1/30 s
```

## Pointer, Scroll, and Layout

- `pointermove` records the latest screen coordinates.
- After `scroll`, `resize`, and container size changes, recompute the position relative to the subject using the same screen coordinates.
- The subject anchor comes from the current `getBoundingClientRect()`; do not cache it forever.
- Pause loops and expensive computation when the subject is out of the viewport.
- Use `IntersectionObserver` to control active state and `ResizeObserver` to update layout.

## Mobile Gyroscope

1. Request permission from a user gesture.
2. Record the first `beta/gamma` as the neutral pose.
3. Rotate the input axes according to screen orientation.
4. Limit outliers and smooth lightly.
5. Do not set a large dead zone by default; handle sensor noise with damping and a small threshold.
6. On permission denial, use touch or a static frame.

## Preloading

- Atlas track: use `<link rel="preload" as="image">`, preload the manifest, static first frame, and atlas, and confirm drawability with `Image.decode()`.
- Video track: preload the static Alpha first frame, video metadata, and the first media segment; allow seeks only after `loadedmetadata`.
- Before loading completes, show the static first frame or a simple loading layer — never multiple stacked frames.
- On asset failure, unlock the page and fall back to the static Alpha image; never expose the green screen.
- Do not let secondary animations block the whole page.

## Performance

- Event listeners use `passive: true` and only update in-memory targets.
- At most one DOM write per frame.
- Do not update styles when the integer frame is unchanged.
- Stop `requestAnimationFrame` when the element is off-screen and the parameter is stable.
- Avoid rendering two large transparent images at once for "smoothness".
- Test cold cache, weak network, low-end phones, page scroll, and fast reverse input.
