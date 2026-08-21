# Green-Screen Video Interaction Track

Read this workflow only when `motion_budget.py` returns `delivery.selected=chroma-video`. It fits one-dimensional sequential access, long timelines, or large-size interaction, and also serves as the fallback primary plan when a one-dimensional random-access asset exceeds the atlas budget.

The video is still green-screen footage. The page generates Alpha in real time via WebGL, so the final background belongs to the page — changing the background does not require regenerating the subject.

## Compiling

Save the auto-selection report first, then compile a uniformly lit green-screen master that has passed content acceptance:

```bash
python3 scripts/motion_budget.py \
  --frames 551 --display 1536x864 --dpr 1 \
  --driver scroll --parameter-space linear \
  --report build/motion-budget.json --strict

python3 scripts/compile_scroll_video.py \
  source/master.mp4 build/chroma-video \
  --budget-report build/motion-budget.json \
  --fps 48 \
  --desktop-width 1920 \
  --mobile-width 1280
```

The script will:

1. Force-interpolate to 48 FPS, keep the green screen, and never bake the page background into the media.
2. Output raw and interpolated contact sheets plus an interpolation report.
3. Clean up loop seams or tail holds as needed.
4. Sample up to 48 evenly spaced frames for Alpha edge analysis and check the actual key color and uniformity from representative frames across the whole clip.
5. Encode all-keyframe MP4s for desktop and mobile, removing audio tracks.
6. Generate a static Alpha fallback image and `compile.json` recording frame count, key color, auto-selection rationale, dimensions, all-keyframe check, and output paths.

On success, regenerable intermediate PNGs are deleted by default, keeping the green-screen master, contact sheets, analysis reports, static Alpha image, and final videos. Pass `--keep-frames` only when debugging interpolation or encoding issues.

All-keyframe increases file size but makes `currentTime` seeks more stable in forward, reverse, and jump directions. Do not switch back to autoplay or emulate scrolling with continuous playback speed.

## Web Integration

Combine the two shared runtimes:

- `assets/interactive-motion.ts`: maps scroll, drag, and other input to integer target frames, and handles damping and speed limiting.
- `assets/chroma-video-renderer.ts`: converts integer frames to `video.currentTime`, waits for the seek to complete, then draws to a transparent Canvas with the WebGL chroma-key shader.

Keep the page structure simple:

```html
<section class="motion-stage">
  <video class="motion-source" muted playsinline preload="auto"></video>
  <canvas class="motion-canvas"></canvas>
</section>
```

```css
.motion-stage { background: var(--page-background); }
.motion-source { display: none; }
.motion-canvas { width: 100%; height: 100%; display: block; }
```

Do not give the video element a final background, and do not show the green-screen video directly to the user.

## Loading and Fallback

- Preload video metadata, the first segment of media, and the static Alpha first frame.
- Frame duration can only be computed after `loadedmetadata`; always submit only the latest integer target frame and discard stale seeks.
- On WebGL, video decode, or asset loading failure, show the static Alpha first frame — the page must never expose the green screen.
- `prefers-reduced-motion` directly shows the static Alpha state that best expresses the content.
- Stop seeking and drawing when the video is off-screen; jump to the latest target frame when it re-enters the viewport.

## Acceptance

- Check edges against white, black, and high-saturation backgrounds to confirm no green fringes, magenta fringes, or false deletions inside the subject.
- Test slow scroll, fast scroll, continuous reverse, first frame, last frame, and cross-section jumps.
- `allFramesAreKeyframes` in `compile.json` must be `true` for both desktop and mobile outputs.
- Record regular seek and fast reverse-seek latency; if the target device visibly drops frames, first lower output resolution to actual CSS size times DPR — never reduce semantic frame density to mask the problem.
- The page should still render correctly after a background change that only touches CSS; if the subject must be regenerated, the delivery pipeline is not acceptable.
