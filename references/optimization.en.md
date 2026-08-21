# Forced Interpolation and Atlas Compression

After the AI motion master passes content acceptance, interpolate first, then continue with cleanup, stabilization, and packaging. Default target is 48 FPS. Keep the original chroma-key master; all outputs go to a new directory.

## Interpolation Gate

```bash
python3 "$OIL_MOTION/scripts/optimize_motion.py" interpolate \
  source/master.mp4 build/interpolated \
  --fps 48 \
  --key auto
```

Outputs include:

- `frames/`: interpolated and keyed Alpha frames.
- `qa/contact-sheet-original.jpg`: original frame contact sheet.
- `qa/contact-sheet-interpolated.jpg`: interpolated contact sheet.
- `qa/analysis-interpolated.json`: interpolated sequence analysis.
- `interpolation-report.json`: automatic before/after comparison.

Both contact sheets must be inspected manually. Stop processing on ghosting, double outlines, edge tearing, part interpenetration, structural distortion, or newly introduced flashes; do not skip interpolation and deliver raw frames.

## Atlas Compression

Continue with `scripts/optimize_motion.py` when transparent-atlas size needs to be controlled. Keep the interpolated Alpha master; compressed output goes to a new file.

## Atlas Target Size

```bash
python3 "$OIL_MOTION/scripts/optimize_motion.py" atlas frames/final \
  --output final/motion.webp \
  --target-mb 2 \
  --display 320x320 \
  --dpr 2 \
  --cell-width 768 \
  --cell-height 768 \
  --columns 16
```

The tool first computes the minimum per-frame pixels from "max CSS display size × DPR", then holds single-frame dimensions and searches for the highest WebP quality; if it cannot hit the target, it may only shrink to that clarity floor. It outputs a same-name manifest and a `.optimize.json` report. `clarityMet` must be `true`; if `targetMet` is `false`, re-run `motion_budget.py`: one-dimensional sequences can switch to green-screen video automatically, while 2D or circular assets lower parameter sampling density or split states. Do not keep shrinking single frames.

## Selection Principles

- Interpolation is mandatory after generating the motion master; default target is 48 FPS.
- Even after the automatic comparison passes, you must still manually review the original and interpolated contact sheets.
- Satisfy parameter sampling density first, then discuss browser refresh rate and damping.
- Do not run final compression before confirming the max actual CSS display size and target DPR.
- Satisfy per-frame clarity at the target DPR before compressing quality; never shrink below the clarity floor to hit a size target.
- Size targets must consider cold cache, device memory, and texture limits — not just network download size.
