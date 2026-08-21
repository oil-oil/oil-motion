# Interactive Animation Creative Method

Read this file when the user asks "what effects are possible", has only a goal with no motion plan, or when an existing animation lacks expressive purpose.

## Start from Function

First decide the primary function the animation serves — pick exactly one main function:

- Guide attention: help the user discover an interactive object.
- Explain relationships: show input, process, causality, hierarchy, or spatial relationships.
- Express progress: make continuous positions, stages, or completion perceivable.
- Provide feedback: confirm hover, drag, submit, success, failure, or waiting.
- Reward exploration: give the user meaningful change after they actively operate.
- Set mood: establish a light, restrained, tense, soft, or mechanical rhythm.

Motion without a function is decoration. Decoration is allowed, but it must be low-cost, pausable, and non-intrusive.

## Audit the Object's Motion Potential First

Do not start from "green screen, spritesheet, parallax, mouse-follow". Inspect the object itself first:

| Dimension | Questions to ask | Common variations |
|---|---|---|
| Structure | What layers, shells, parts, and connections make it up? | assemble, disassemble, explode, cutaway, fold, unfold |
| Function | What are the inputs, processing, and outputs? | start, transfer, compute, charge, respond, complete |
| Material | Can surface and interior change visibility? | transparent, x-ray, wireframe, liquid, melt, crystallize |
| Space | Where should the user look from and to? | orbit, dolly in, pull back, fly-through, enter interior, cross scale |
| State | What do the before/after states mean? | on/off, empty/full, fast/slow, old/new, normal vs pro mode |
| Information | Which relationships need to be understood? | split, converge, map, causality, compare, hierarchy, feedback |

A phone can go from a complete exterior to an exploded view, into the chip's interior, light up along signal paths, then reassemble.
A software product can go from its UI into the data pipeline, show the processing, then return to results. The examples only illustrate the method — they are not the Skill's default subject matter.

## Motion Grammar

Choose verbs below that express the content; do not cram every change into one animation:

- Structure: assemble, disassemble, explode, separate, stack, fold, unfold, peel, cutaway.
- Form: morph, inflate, compress, grow, dissolve, crystallize, flow.
- Material: reveal, x-ray, wireframe, scan, heatmap, translucent.
- Space: orbit, dolly, macro, fly-through, tunnel, parallax, scale-jump.
- Information: trace, route, pulse, branch, converge, compare, highlight.
- State: activate, charge, complete, unlock, switch, transform.

## Map Input to Change

| Input | Continuous parameter | Suitable visual response | Parameter structure |
|---|---|---|---|
| scroll | page or section progress, velocity | disassemble, assemble, fly-through, material, chapter transitions | linear |
| pointer | direction, distance, velocity | orbiting view, focus part, cutaway depth, light scan | circular / 2d |
| drag | displacement, angle, stretch | direct separation, tear, rotate, before/after compare | linear / 2d |
| touch / orientation | tilt, direction, force | gravity, interior layer shift, liquid, spatial parallax | 2d |
| audio | volume, spectrum, beat | spectral structure, pulse, deformation, arrangement | linear / data |
| data / state | value, stage, success/failure | flow, heatmap, completion, mode switch | linear / discrete |

For the same object, consider at least three kinds of direction: structural change, spatial or camera change, and material or state change. When the user has already specified the motion, do not add unrelated directions just to pad the count.

## Turn Ideas into Keyframes

Oil Motion's visual production is fixed as "generate images first, then video". Each direction must answer first:

1. What the start image is.
2. What the end image is.
3. Whether intermediate keyframes are needed for the change to be stable.
4. Which two adjacent keyframes form one video segment.

- When a real product's logo, hole positions, part counts, and proportions must not drift, generate and accept every keyframe from the original product images first — do not let the video model guess the endpoint from text alone.
- One video segment completes only one main semantic change, e.g. "whole unit separates" or "camera enters the chip". Do not cram multiple big changes into one segment.
- Multi-stage narratives use `K0 → K1 → K2…`: generate all keyframes first, then generate the `K0→K1`, `K1→K2` videos separately.
- Text, numbers, progress, and highlights are overlaid programmatically at runtime; the main visuals and transitions still come from keyframe-constrained AI video.

For example, "phone complete → exploded view → chip close-up → reassembled" needs four keyframes and three video segments, not one long prompt. This makes each segment more stable and easier to scrub forward/backward and redo individually.

## Make Three Directions Truly Different

Three directions must differ in at least two aspects:

- Different driving method.
- Different parameter space.
- Different expressive function.
- Different motion subject or structure.
- Different key states or camera path.

Avoid offering three variants that only differ in speed, amplitude, or color.

## Semantic vs Geometric Judgment

- Part connections, shell opening, material deformation, joints, grasping, hair, cloth, and occlusion are semantic motion.
- Displacement, scale, rotation, cropping, path, inertia, and parameter mapping are geometric motion.
- Whenever moving the whole image would break contact or occlusion relationships, generate a full semantic action.
- Displacement, timing, text, and parameter mapping go to the program; the subject's main visual change is still generated by AI video.

## Choose Complexity by Display Scale

- Small controls: short motion, clear silhouette, explicit states; generate only the necessary short segments and few frames.
- Content illustration: allow one main semantic action; control duration and asset size.
- Hero or full-screen narrative: run asset budgeting first; long linear narratives usually auto-select green-screen video + WebGL real-time keying; small or random-access animations use an Alpha atlas.
- Long-page continuous scroll: distinguish full-page progress from local section progress; do not map the whole page to one video by default.

## Generate Creative Directions

Directions must come from evidence about the object, not from a previous project. Write out each direction:

1. Start and final states.
2. Which structures or materials genuinely change.
3. Whether the camera moves, and what its trajectory is.
4. How input maps to progress, and whether the reverse operation holds.
5. Which visuals are locked by keyframe images, which intermediate changes are generated by AI video, and which text and interaction is program-controlled.
6. Clarity, frame count, and performance cost at the target size.

## Creative Quality Gate

Reject the following directions:

- User input has no comprehensible relationship to the visual change.
- The animation only autoplays, with no new information or feedback from interaction.
- The still state does not hold; it must keep moving to be understood.
- Simple geometric motion implemented with expensive raster video.
- Force-fitting an incompatible parameter model just to reuse an existing video.
- Only valid at demo size; meaningless when scaled down or on touch.

Once a direction is chosen, convert it into a Motion Brief, then proceed to asset budgeting, generation, and implementation.
