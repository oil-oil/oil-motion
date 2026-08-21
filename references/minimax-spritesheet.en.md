# MiniMax Video to Interactive Spritesheet

Execute this workflow only when `motion_budget.py` returns `delivery.selected=alpha-atlas`. It turns reference images into a continuous-motion master through ZenMux's MiniMax video API, then compiles it into randomly accessible transparent frames, a WebP atlas, and a web interaction.

## Inputs and Deliverables

Before starting, you must have:

- A first frame already verified for size and composition on the target page.
- A clear `driver`, `parameter_space`, motion direction, still state, and whether it is a loop.
- Final CSS display size, target DPR, and a frame-count or duration budget.
- When identity must be locked, bake identity information into the first/last keyframes at image-generation time; the first/last-frame mode cannot carry additional reference images.

When done, you must deliver:

```text
motion-name/
├── source/
│   ├── first-frame.png
│   ├── last-frame.png            # required for one-way transitions
│   ├── identity.png              # image-generation phase or reference-only mode
│   ├── prompt.txt
│   ├── master.mp4
│   └── master.job.json
├── frames/
│   ├── raw/
│   └── final/
├── qa/
│   ├── raw-analysis.json
│   ├── raw-contact.jpg
│   ├── final-analysis.json
│   └── final-contact.jpg
└── final/
    ├── motion.webp
    ├── motion.json
    └── implementation.*
```

## Parameter Selection

| Goal | First frame | Last frame | Reference image | Recommendation |
|---|---|---|---|---|
| Seamless loop | Required | Same as first, via `--loop-frame` | Forbidden | Generate one circle only; no pause, no return |
| One-way transition | Required | Required and different | Forbidden | Do not return after reaching the last frame |
| Direction following | Required | Same as first when looping | Forbidden | Generate a full direction ring; runtime maps the angle |
| Scroll narrative | Required | Recommended | Forbidden | Every frame should be a stay-able state |
| Reference-only generation | Forbidden | Forbidden | One or more allowed | Does not lock exact first/last states |
| Existing qualified video | Not needed | Not needed | Not needed | Skip generation; start from detection and frame extraction |

The default model is `minimax/minimax-h3`; start at `768p` resolution to validate motion, and use `2K` only if final clarity is insufficient. Single-variable motions default to 3–6 seconds.

- Do not pass `--model`; the script is fixed to `minimax/minimax-h3`.
- Without `--ratio`, the script infers the nearest common aspect ratio from the first frame or first reference image; without images it defaults to `1:1`. Pass a special ratio explicitly when needed.
- `reference_image` is mutually exclusive with `first_frame` / `last_frame` / `loop_frame`. Mixing them triggers MiniMax API error `2013`, and `video_job.py` blocks the submission before reaching the network.
- When first/last-frame transitions need consistent identity, both keyframes must share the same reference and composition from the image-generation phase; do not re-attach `reference_image` in the video request.
- Default `duration` is 5 seconds. Do not pass `--frames` alongside it to chase frame counts; when only `--frames` is passed, the script no longer sends `duration`.
- Use `--frames` only when the current API explicitly supports frame-count control; if the API rejects the parameter, save the error and report it — never silently drop the first frame, last frame, or reference image.
- `seed` is only used for reproducibility when the model supports it; it cannot replace reference images and first/last frames.
- One video carries one continuous parameter only. Two-dimensional input uses 2D sampling or multiple clips — do not force it into a single out-and-back video.

## Standard Execution Flow

Set the Skill path first, then check whether the API key is configured:

```bash
OIL_MOTION="/absolute/path/to/oil-motion"
python3 "$OIL_MOTION/scripts/oil_motion_config.py" status
```

If not configured, guide the user through running
`python3 "$OIL_MOTION/scripts/oil_motion_config.py" set` once. The script hides the input and saves the key in a local config file. Reuse it for later tasks without asking again, and never write the key into the project, prompts, command arguments, logs, or task metadata.

### 1. Budget Gate

```bash
python3 "$OIL_MOTION/scripts/motion_budget.py" \
  --frames 120 \
  --display 180x180 \
  --dpr 2 \
  --max-texture 4096 \
  --driver pointer \
  --parameter-space circular \
  --report build/motion-budget.json \
  --strict
```

Stop conditions:

- `delivery.selected` is not `alpha-atlas`; stop reading this workflow and switch to `chroma-video.en.md`.
- Minimum per-frame pixels are above the planned atlas cell.
- A single atlas exceeds the texture or decode-memory budget.
- The static first frame has cropping, blur, ratio, or anchor problems on the target page.

### 2. Write and Accept the Prompt

Read [prompting.en.md](prompting.en.md) and combine in order:

1. Identity and style locking.
2. Locked camera and locked anchor.
3. The single motion variable, direction, start, and end.
4. Green-screen requirements.
5. Negative constraints against the current failure risk.

The prompt must not ask the model to output transparency channels, frame numbers, atlases, or precise compression; the program handles those.

### 3. Submit to MiniMax

Loop:

```bash
python3 "$OIL_MOTION/scripts/video_job.py" \
  --prompt-file source/prompt.txt \
  --first-frame source/first-frame.png \
  --loop-frame \
  --resolution 768p \
  --ratio 1:1 \
  --duration 5 \
  --seed 42 \
  --output source/master.mp4 \
  --metadata source/master.job.json
```

One-way transition:

```bash
python3 "$OIL_MOTION/scripts/video_job.py" \
  --prompt-file source/prompt.txt \
  --first-frame source/first-frame.png \
  --last-frame source/last-frame.png \
  --resolution 768p \
  --ratio 1:1 \
  --duration 5 \
  --output source/master.mp4 \
  --metadata source/master.job.json
```

Stop and report the specific response when the model or API rejects parameters. Only after the user agrees to a downgrade may you remove constraints or change models.

Even when the API receives `generate_audio=false`, the returned file may still contain an AAC audio track; interactive asset packaging must explicitly use `-an`. A 5-second request may also return a slightly longer clip with a tail hold, so always read the actual detection results — never use request parameters in place of the real frame count.

### 4. Master Gate

```bash
python3 "$OIL_MOTION/scripts/motion_pipeline.py" probe source/master.mp4
```

Watch the full video; do not look at only the first and last frames. Regenerate and skip media processing when any of the following appear:

- Semantic errors in identity, structure, logo, limbs, or props.
- Wrong motion direction, mid-way reversal, pauses, hard cuts, or a last-moment jump back to the first frame.
- Visible drift in camera, perspective, subject scale, lighting, or chroma-key background.
- The subject touches the frame edges and cannot be keyed safely.

The program can only fix minor position, size, color, and duplicate-frame issues — not wrong motion semantics.

### 5. Forced Interpolation, Keying, and Inspection

```bash
python3 "$OIL_MOTION/scripts/optimize_motion.py" interpolate \
  source/master.mp4 build/interpolated \
  --fps 48 \
  --key auto

python3 "$OIL_MOTION/scripts/motion_pipeline.py" contact build/interpolated/frames \
  --output qa/interpolated-contact.jpg \
  --columns 8
```

You must inspect `build/interpolated/qa/contact-sheet-original.jpg`,
`build/interpolated/qa/contact-sheet-interpolated.jpg`, `build/interpolated/interpolation-report.json`, and
`qa/interpolated-contact.jpg`:

- Four corners transparent, no false deletions inside the subject, no obvious green or magenta fringes on edges.
- Frame order matches the motion direction.
- No empty frames, brightness flashes, size jumps, center jumps, or abnormal duplicated segments.
- No ghosting, double outlines, edge tearing, part interpenetration, or structural distortion.

Interpolation is mandatory. Stop processing on uneven backgrounds, heavy subject false-deletion, or interpolation artifacts — do not skip interpolation and deliver raw frames.

### 6. Loop Cleanup and Optional Stabilization

Loop animation:

```bash
python3 "$OIL_MOTION/scripts/loop_cleanup.py" \
  build/interpolated/frames frames/clean \
  --seam-window 24 \
  --duplicate-threshold 0.003 \
  --report qa/loop-cleanup.json
```

Stabilize only when a fixed subject drifts slightly:

```bash
python3 "$OIL_MOTION/scripts/motion_pipeline.py" normalize \
  frames/clean frames/final \
  --anchor bottom \
  --max-scale-change 0.08
```

When loop cleanup or stabilization is not needed, copy the qualified interpolated sequence to `frames/final`. Free motion, camera movement, and real perspective changes must not be stabilized.

### 7. Final Gate and Atlas

```bash
python3 "$OIL_MOTION/scripts/motion_pipeline.py" analyze frames/final \
  --output qa/final-analysis.json

python3 "$OIL_MOTION/scripts/motion_pipeline.py" contact frames/final \
  --output qa/final-contact.jpg \
  --columns 8

python3 "$OIL_MOTION/scripts/motion_pipeline.py" atlas frames/final \
  --output final/motion.webp \
  --manifest final/motion.json \
  --cell-width 360 \
  --cell-height 360 \
  --quality 88
```

Re-run the budget check before packaging:

```bash
python3 "$OIL_MOTION/scripts/motion_budget.py" \
  --frames 120 \
  --display 180x180 \
  --dpr 2 \
  --cell 360x360 \
  --max-texture 4096 \
  --driver pointer \
  --parameter-space circular \
  --report final/motion-budget.json \
  --strict
```

Package only when the budget still returns `alpha-atlas` and passes. The numbers above are only a complete example that fits a 4096 texture; real projects must recompute with the Motion Brief's display size, DPR, driver, parameter space, and final frame count. If auto-selection flips to `chroma-video`, stop atlas packaging and run the video track; for over-budget 2D parameters, lower sampling or split states and re-budget — never lower single-frame clarity or squeeze 2D semantics into a video.

### 8. Web Implementation and Acceptance

Copy the runtime from `assets/interactive-motion.ts`:

- Decode the still frame and key atlas first, then show the interactive layer.
- Input only updates the target parameter; write at most one integer frame per `requestAnimationFrame`.
- Circular motion uses the shortest circular distance.
- Use `smoothDamp` with a velocity state and max speed — do not stack multiple `lerp`s.
- Recompute input relative to the subject after scrolling, zooming, and device rotation.
- Provide a `prefers-reduced-motion` static frame and asset-failure fallback.

At minimum verify: cold cache, slow input, fast reverse, one full circle around the subject, mouse held still after page scroll, window resize, mobile, and low-performance devices. Any flicker is located in the order "master → frames → atlas → mapping → decode".

## Reports That Must Not Be Omitted

When delivering, explicitly list:

- The Motion Brief and parameter model.
- The final prompt plus first frame, last frame, and reference images.
- MiniMax model, resolution, duration, seed, and task metadata path.
- Actual processing commands, raw frame count, cleaned frame count, and anomaly reports.
- Auto-selection result and rationale, plus final atlas dimensions, cell dimensions, and decode-memory estimate.
- Web mapping, preload, damping, speed limiting, and fallback strategy.
