# Animated Motion Explainer Page

Use `scripts/create_explainer.py` to generate a standalone HTML page when you need to explain clearly how "a master video becomes an interactive animation". Do not copy a project's roles, copy, or layout; the page reads only the atlas structure and driver config.

## What the Page Contains

- The full spritesheet on the left, zoomable and draggable, highlighting the frame actually rendered on the right.
- An optional "Master Video" tab for comparing the AI video with the compiled web asset.
- The live animation, frame number, row/column position, and the input mapping formula on the right.
- Desktop uses a 2:1 layout; mobile stacks vertically automatically.
- Display only after the atlas finishes decoding, to avoid first-frame flicker.

## Drivers

| `--driver` | Input | Suitable material |
|---|---|---|
| `pointer-angle` | direction of the pointer relative to the subject | circular direction, orientation, knobs |
| `pointer-x` | horizontal pointer position in the preview area | linear pose, before/after comparison |
| `drag` | horizontal drag distance | grabbable products, frame-by-frame inspection |
| `scroll` | page scroll progress | chapter transitions, product disassembly, one-shot through |
| `autoplay` | time | idle, looping motion, no-interaction display |

`pointer-angle` uses wrap-around and the shortest circular distance. Other interactions default to a linear sequence with start and end points. Autoplay supports `loop`, `pingpong`, and `once`.

For scroll mode, run `motion_budget.py --scroll-pages <pages> --strict` before generating. Material is prepared at 24 frames per screen by default; below roughly 20 frames/screen, long scrolls show a perceivable frame-stepping ladder that cannot be hidden by just lowering `smooth-time`.

## Generation

Atlas URL and video URL are written into the HTML final, both relative to the output HTML's directory. The manifest is a local JSON read at generation time and is not requested by the browser at runtime.

```bash
OIL_MOTION="$HOME/.codex/skills/oil-motion"

python3 "$OIL_MOTION/scripts/create_explainer.py" \
  --title "One image, 240 directions." \
  --manifest final/motion.json \
  --atlas-url ../final/motion.webp \
  --video-url ../source/master.mp4 \
  --driver pointer-angle \
  --output motion-explainer.html
```

Without a manifest, pass grid parameters directly:

```bash
python3 "$OIL_MOTION/scripts/create_explainer.py" \
  --atlas-url ./motion.webp \
  --frames 96 \
  --columns 12 \
  --rows 8 \
  --cell-width 320 \
  --cell-height 320 \
  --driver scroll \
  --scroll-pages 4 \
  --output scroll-explainer.html
```

Autoplay:

```bash
python3 "$OIL_MOTION/scripts/create_explainer.py" \
  --atlas-url ./idle.webp \
  --frames 48 --columns 8 --rows 6 \
  --driver autoplay \
  --autoplay-fps 18 \
  --autoplay-mode pingpong \
  --output autoplay-explainer.html
```

The script stops by default when the output already exists; pass `--force` after confirming the target.

## Acceptance

1. Open the page via a local HTTP server, not only `file://`.
2. Check that the current frame on the right strictly matches the highlighted cell on the left.
3. Check first frame, last frame, fast reverse, and circular seam.
4. The video tab plays when switched to, and the video pauses when switching back to the atlas.
5. Scroll-mode pages actually have scroll distance and progress covers 0 to 1 completely.
6. At 0%, 50%, and 100%, check that the frame number on the right strictly matches the highlight on the left, and scroll back quickly to confirm no dropped frames or obvious stepping.
7. On mobile, check layout, touch drag, and the reduced-motion static fallback.
