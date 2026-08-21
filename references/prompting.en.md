# AI Video Motion Prompts

## Fixed Workflow: Generate Images First, Then Video

Do not generate a complete motion from a text prompt alone. First complete:

1. Generate and accept the start keyframe from the original reference images.
2. Generate and accept the end keyframe from the same reference images.
3. For complex narratives, generate all intermediate keyframes `K1…Kn` first.
4. Submit each pair of adjacent keyframes as first/last frames to MiniMax.
5. After accepting each video, the program cuts frames, joins, compresses, and maps the interaction.

A video prompt only describes how to change continuously between two already-decided images; it no longer designs the endpoint. Subject identity, product structure, logos, composition, and style must be resolved in the keyframe images first.

## Decide Before Writing the Prompt

Write out first:

1. Which continuous parameter drives the animation.
2. The parameter's start, end, and direction.
3. Which parts of the subject may change and which must stay fixed.
4. Whether it is a loop.
5. Whether to use a green or magenta key, and how to guarantee uniformity across the four corners and the time dimension.
6. How the subject overlays the page background as an Alpha layer after keying.
7. Whether frames are finally sampled by time, angle, 2D position, or state.

The generation model is responsible for motion semantics and visual continuity — not precise frame cutting, transparency channels, frame numbers, compression, or atlases.

## Choose First/Last-Frame Mode or Reference-Image Mode Correctly

MiniMax H3's two image-input modes are mutually exclusive; never mix them:

- `first_frame` decides the start composition, character position, proportions, camera, and background.
- `last_frame` decides the frame the motion must finally reach.
- `reference_image` is only for reference-generation mode without first/last frames.
- `seed` reduces unrelated variation when re-running and doing local fixes.
- `return_last_frame` is for automatically comparing first/last differences.

Precise interactive animation defaults to first/last-frame mode. When identity, face, clothing, product details, or illustration style must be locked, generate and accept consistent keyframes in the image-generation phase first — do not attach `reference_image` in the video request. Mixing triggers API error `2013`.

For loop motion, prefer passing **the same accepted composition** as both first and last frame, then describe the full circle's direction, speed, and occlusion changes in the prompt. Different first/last frames fit one-way transitions, not seamless loops.

First/last-frame constraints are not a free pass: the model may still reverse mid-way, pause, generate extra limbs, or snap back to the first frame in the final frames. You must inspect the full video, contact sheets, duplicate-frame distribution, and first/last differences.

## Generic Identity-Locking Block

Place the following before the motion description and replace the angle brackets:

```text
Use the supplied first and last frames as the exact identity and design
references for <SUBJECT>. Preserve the same silhouette, anatomy, face, clothing or product
geometry, colors, line work, texture, and proportions in every frame. The
subject remains the same size and at the same anchored position throughout the
shot. Do not add, remove, duplicate, or redesign any body part, accessory,
feature, logo, control, or prop.
```

If the subject is an illustration, add:

```text
Preserve the original illustration style exactly. Keep line thickness,
halftone texture, flat color regions, and edge sharpness consistent. Do not
turn the subject into volumetric CGI, photorealistic, painterly, or glossy imagery.
```

## Locked-Camera Block

```text
Locked camera and locked framing. No camera pan, tilt, zoom, orbit, shake,
reframing, perspective change, lens change, depth of field, or lighting change.
The body and contact point remain fixed. Only <ALLOWED_PARTS> may move.
```

Remove this block only when the camera movement itself is what scroll controls, and describe the camera trajectory explicitly.

## Green-Screen Block

Default to `#00FF00`. Switch to `#FF00FF` when the subject contains green.

```text
The entire background is one perfectly uniform flat chroma-key <KEY_COLOR>
rectangle in every frame. No gradient, texture, noise, floor plane, horizon,
shadow, reflection, glow, particles, color variation, or lighting falloff on
the background. Keep the subject fully separated from all image borders with
generous padding. No cast shadow. No green/magenta object or reflected spill on
the subject. No text, subtitle, watermark, border, or UI.
```

The model may not strictly generate the exact color value, so uniformity across the corners and the time dimension matters most. Later scripts sample the real background color from edges.

## Circular Direction Animation

Fits gaze, head turns, product orientation, knobs, and 360° display:

```text
Create one continuous clockwise directional cycle. Start with <SUBJECT> looking
oriented toward <START_DIRECTION>. An invisible target moves at a constant
angular speed around the subject through a complete 360-degree circle, and
<SUBJECT> follows it smoothly with <ALLOWED_PARTS>. Pass through every
intermediate direction without pausing, snapping, reversing, returning to the
front early, or holding any direction. End at the same pose and direction as
the first frame so the cycle joins cleanly. Keep <FIXED_PARTS> completely still.
Use natural anatomical deformation, but no secondary idle motion, blinking,
breathing, tail movement, or unrelated action.
```

When the runtime does not need a loop, use instead:

```text
Move once continuously from <START_DIRECTION> to <END_DIRECTION>. Do not return
to the start and do not pause at intermediate directions.
```

## Product Disassembly and Exploded View

Generate the complete-state and exploded-state images separately from the real product reference first. Only after both pass manual acceptance, use them as exact first/last frames; do not let the video model invent the final structure from text.

```text
Use the supplied first and last frames as exact geometry, identity, material,
logo, component-count, alignment, camera, lighting, and composition references.
Create one continuous transformation from the fully assembled <PRODUCT> to the
approved exploded view. Separate the existing shell, display, battery, boards,
connectors, cameras, and fasteners only along their physically plausible axes.
Preserve every component's exact shape, scale, orientation, color, and relative
order. Keep all parts readable and non-overlapping at the final state. No new,
missing, duplicated, melted, or redesigned components. No cuts, camera changes,
scale breathing, motion blur, labels, or unrelated motion. Every intermediate
frame must be a stable reversible assembly state suitable for scroll scrubbing.
```

Explosion direction, spacing, part count, and final composition must be decided in the last-frame image first. The video is responsible for a continuous transition from the complete state to that last frame; text labels, numbers, and part highlights are overlaid programmatically after generation, to avoid AI video generating unstable text.

## Camera Fly-Through

When the camera motion itself is the interactive content, drop the locked-camera block and define an explicit reversible trajectory instead:

```text
Create one continuous forward camera move from <START_VIEW> to <END_VIEW>.
Follow the supplied path through <ORDERED_LANDMARKS> without cuts, orbiting,
sideways drift, speed jumps, focus pumping, or lens changes. Keep product
geometry, lighting, scale relationships, and landmark positions consistent.
Every frame must remain sharp and readable when scroll playback stops. The
reverse frame order must also form a natural backward move.
```

For long-distance fly-throughs, do not give only the start and end. Generate intermediate keyframes along the path first to keep the subject, spatial landmarks, scale, and style consistent, then generate short videos between adjacent keyframes separately.

## Multi-Segment Keyframe Chaining

Build `K0 → K1 → K2…Kn` first:

- `Ki` and `Ki+1` are the exact first/last frames of segment `i`.
- All keyframes reuse the same reference images, aspect ratio, style constraints, and subject proportions.
- Each segment describes only one main change, usually 3–6 seconds long.
- The model's returned last frame may feed the next segment only if it matches the accepted `Ki+1`; otherwise keep using the original `Ki+1` so errors do not accumulate segment by segment.
- Inspect seams frame by frame after joining; if a seam is unstable, redo that short segment — not the whole timeline.

## Pointer 2D Animation

2D input cannot be accurately expressed by a single left-right head-turn video. Prefer these options:

### Option A: Angle Is Enough

Have the video generate a full direction ring; the runtime maps the angle with `atan2(y, x)`. Distance only affects smoothing speed or return strength, not the pose.

### Option B: 2D Sampling

Generate multiple short clips or key poses on a fixed grid, for example:

```text
Generate the same subject and framing for target position <X_POSITION>,
<Y_POSITION>. Keep the exact body anchor, subject scale, lighting, style, and
background used in every other grid sample. Move only <ALLOWED_PARTS> toward
that target and settle naturally. No entrance or exit motion.
```

The 2D grid covers at least top-left, top, top-right, left, center, right, bottom-left, bottom, and bottom-right. Unify anchor and size programmatically, then do bilinear neighborhood selection or interpolation. Do not ask the model to traverse the grid in one video and then access it randomly.

## Scroll Timeline Animation

Fits product disassembly, page narratives, chart expansion, and scene transitions:

```text
Create a single continuous transformation designed for frame-by-frame scroll
scrubbing. At frame 0, <START_STATE>. Over the shot, <ORDERED_CHANGES>. At the
last frame, <END_STATE>. Every intermediate frame must be a meaningful stable
progress state. Use constant visual continuity with no cuts, dissolves, sudden
jumps, duplicated holds, camera shake, motion blur, or unrelated motion. Keep
the composition readable when playback is stopped on any frame.
```

Write multiple changes as relative progress phases, e.g. `0–35%` completes the first phase, `35–80%` advances the main relationship, `80–100%` reaches the final state. Require continuous change in every phase and explicitly forbid the model from finishing the main motion early in the front and leaving near-duplicate frames at the tail. Percentages constrain rhythm; they do not require the model to output exact frame numbers. The real rhythm still needs inspection via contact sheets, trimming or re-timing when necessary.

Scroll sequences do not necessarily need 24–60 FPS. Prefer generating clear semantic key phases, then let the program decide frame sampling density.

## Discrete-State Animation

Generate each state separately; never let one long video contain hover, click, success, and failure at once:

```text
Create a short transition from the exact neutral pose to the exact <STATE>
pose. The first frame must match the shared neutral reference exactly. Hold the
final pose only briefly. No camera movement, no unrelated idle motion, and no
return transition.
```

Prefer program-side reverse playback for reverse states; generate separately only when reverse playback violates physics.

## Product 360° Prompt

```text
Use the provided product image as the exact geometry, material, color, logo,
control, and proportion reference. Rotate the product once clockwise around its
vertical center at a constant angular speed. Locked orthographic-like camera,
fixed scale, fixed center, fixed lighting, no perspective breathing, no added
details, no deformation, no text changes, no logo changes. The first and last
frames join exactly.
```

## Failure-Fix Prompts

Fix one problem at a time while reaffirming all invariants:

```text
Keep the subject identity, design, style, camera, framing, scale, anchor,
background, lighting, and correct motion unchanged. Fix only this issue:
<ONE_PRECISE_ISSUE>. Do not add any new motion or detail.
```

Common fixes:

- `Keep every approved component unchanged; remove the duplicated connector.`
- `Keep the body fixed; eliminate scale pulsing and center drift.`
- `Remove the one-frame brightness flash; lighting is identical in every frame.`
- `Continue through the angle without pausing or snapping.`
- `Make the last frame match the first frame exactly for a seamless loop.`

## Negative Constraints

Add as needed; do not mechanically copy all of them:

```text
No cuts, morphing, identity drift, scale breathing, position drift, duplicated
limbs, missing limbs, extra objects, blinking, idle sway, motion blur, ghosting,
frame blending, lighting flicker, shadows on the background, camera movement,
text, watermark, border, or style change.
```

## Resolution and Duration

- Generate 3–6 second single-variable motions first; long sequences drift more easily.
- Use 2× the final display size as the minimum master resolution.
- The generation model is only responsible for the continuous-motion master; after the master passes content acceptance, the program interpolates uniformly with a default target of 48 FPS. Do not ask the model to raise frame rate itself.
