# Quality Checks and Fault Location

## Inspection Order

Check in the order master video, interpolation result, transparent frames, stabilized frames, atlas, runtime. When upstream material has problems, do not mask them at runtime.

## Master Video

- Identity, clothing, product geometry, and colors are consistent.
- The subject has no extra or missing limbs, props, or structures.
- Subject size, center, and anchor have no breathing drift.
- Camera, focal length, perspective, and lighting are consistent.
- Motion has no pauses, reversals, hard cuts, or unnecessary idle actions.
- Loop sequences have matching first/last poses.
- The chroma-key background is uniform across corners and the time dimension.

## Interpolation Result

- View both the original and interpolated numbered contact sheets.
- Target frame rate matches the Motion Brief, default 48 FPS.
- No ghosting, double outlines, edge tearing, part interpenetration, or structural distortion.
- Interpolation did not add empty frames, brightness flashes, size jumps, or center jumps.
- A passing automatic report does not equal a passing manual review; stop on artifacts, and do not skip interpolation to deliver raw frames.

## Keying Result

- Image mode is RGBA.
- Corner alpha is 0.
- Hair, glasses, line work, ears, tails, and small props are complete.
- No green or magenta spill on edges.
- Whites and halftones inside the subject are not falsely deleted.
- No obvious alpha-edge jumping between adjacent frames.

If the background itself is uneven, regenerating the master is usually safer than widening the keying threshold.

## Analysis Report

`motion_pipeline.py analyze` reports:

- alpha bounding box, subject center, fill ratio, and brightness.
- adjacent-frame differences.
- size jumps, center jumps, brightness flashes, empty frames, and near-duplicate frames.

Warnings are location clues, not auto-delete instructions. Slow motion can legitimately produce near-duplicate frames.

## Common Problems

### A Frame Flashes at Some Angle

Check in order:

1. Whether the master has a single-frame brightness or deformation anomaly.
2. Whether file names sort numerically instead of as strings.
3. Whether atlas cell size, column count, and frame count match the runtime.
4. Whether the circular start angle is mapped off by a constant.
5. Whether the last frame to first frame is truly continuous.
6. Whether an image layer cross-fades or an old frame was not removed.
7. Whether frames switch before the atlas finishes decoding.

### Head or Product Size Changes

- Prefer regenerating with emphasized fixed proportions, fixed camera, and fixed anchor.
- Fixed-body orientation animations can use `normalize` for light stabilization.
- Keep `max-scale-change` restrained; over-stabilizing makes the silhouette twitch.
- Do not stabilize free motion, camera push-ins, or real perspective changes.

### Animation Feels Sticky

- Do not stack multiple lerps.
- Use `smoothDamp` with a velocity state.
- Lower `smoothTime` moderately while raising `maxSpeed`.
- Confirm the target frame updates on every input, with no oversized input dead zone.
- Do not wait on image requests during fast movement; all random-access frames should already be preloaded.

### Animation Too Fast, Unnatural

- Limit max frame speed.
- Keep a velocity state; do not set the current frame directly to the target frame.
- The motion master needs continuous intermediate poses; missing frames cannot be fixed by slowing down alone.

### Ghosting on First Move

- Do not use transparent cross-fade between two frames.
- The initial frame must come from the same atlas.
- Wait for the atlas to finish decoding before allowing interaction.
- On first input, smoothly track the target frame from the current frame.

### New Version Is Blurry

- Check whether master resolution dropped.
- Check whether repeated scaling happened during frame cutting or stabilization.
- Check whether atlas cells are smaller than the actual display size.
- Check WebP quality, lossy transparent compression usage, and browser zoom factor.
- Rebuild from the high-resolution master; do not extract backward from the web atlas.

### Wrong Pointing After Scroll

The pointer's screen coordinates did not change, but the subject's screen position did. On scroll, re-read the subject rectangle and recompute the relative vector.

## Atlas Acceptance

- The manifest's `frameCount`, `columns`, `rows` match the actual atlas.
- Each cell contains exactly one complete frame.
- Empty cells are transparent.
- The atlas does not exceed the target device's texture limit.
- Frame order in the contact sheet matches the interaction parameter direction.

## Runtime Acceptance Matrix

At minimum test:

- Desktop mouse slow, fast, continuous reverse, and one full circle around the subject.
- Mouse held still after page scroll.
- Window resize and landscape/portrait changes.
- Mobile touch and gyroscope: granted, denied, and unavailable cases.
- Cold cache, slow network, asset load failure.
- `prefers-reduced-motion`.
- Page recovery after switching to background.

## Suggested Budgets

Budgets should be adjusted per project; these are only first-pass references:

- Keep compressed above-the-fold animation assets around 1–4 MiB.
- Total above-the-fold critical asset wait limit 4–6 seconds, with a static fallback.
- Keep atlas dimensions at most 4096×4096.
- Actual display size must not exceed source cell size; reserve about 2× pixels for high-DPR screens.
- No network requests during the loop; no repeated DOM writes for the same frame.
