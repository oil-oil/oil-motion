# Auto-Selecting the Delivery Method

Oil Motion always uses the same green-screen production chain; the only fork is at the web delivery stage:

- `alpha-atlas`: offline keying at build time; the page reads an Alpha atlas.
- `chroma-video`: keeps the green-screen video; the page keys it in real time with WebGL.

This is the Agent's build decision, not a user option. Do not ask the user "video or spritesheet", and do not implement both primary plans at once for convenience.

## The Budget Script Is Mandatory

Pass the Motion Brief's real parameters to the script:

```bash
python3 scripts/motion_budget.py \
  --frames 551 \
  --display 1536x864 \
  --dpr 1 \
  --driver scroll \
  --parameter-space linear \
  --scroll-pages 8 \
  --report build/motion-budget.json \
  --strict \
  --json
```

Read `delivery.selected`, `delivery.reasonCodes`, and `delivery.thresholds`. The file saved by `--report` is a mandatory input to later compilation, and the runtime implementation must match the selection result.

## Fixed Decision Order

1. `parameter_space=2d`: select `alpha-atlas`. Two-dimensional input needs grid random access and cannot be squeezed into one linear video.
2. `parameter_space=discrete`: select `alpha-atlas` within budget; when over budget, split into independent states or transitions and budget each separately — never stitch unordered states into one video.
3. Random access and both the single-atlas and decode memory fit within budget: select `alpha-atlas`.
4. One-dimensional sequential access with no fewer than 180 frames: select `chroma-video`.
5. The theoretical Alpha atlas of a one-dimensional asset exceeds a single 4096 texture or 192 MiB decode memory: select `chroma-video`; if it is random access, add fast-jump and reverse-seek acceptance.
6. Remaining small assets: select `alpha-atlas`.

Default thresholds come from `motion_budget.py` and can be adjusted via command-line arguments based on explicit target-device constraints — but never adjusted based on whether the user is technical.

## Two Typical Results

Small mouse-direction ring:

```bash
python3 scripts/motion_budget.py \
  --frames 96 --display 240x240 --dpr 1 \
  --driver pointer --parameter-space circular --strict
```

Should select `alpha-atlas`, because it needs fast random reverse and a single atlas can handle it.

Full-screen long scroll:

```bash
python3 scripts/motion_budget.py \
  --frames 551 --display 1536x864 --dpr 1 \
  --driver scroll --parameter-space linear --strict
```

Should select `chroma-video`, because the linear timeline is long and the atlas's theoretical decode memory and texture count are far above the video track's.

## Over-Budget Handling

- `alpha-atlas` selected but the report fails: for 2D input, reduce sampling density or adjust the confirmed display size; for discrete input, split into independent states or transitions. Then re-budget — never silently lower single-frame clarity.
- `chroma-video` selected: do not generate full Alpha PNGs or a large atlas as the primary asset; keep only the QA frames and the static Alpha fallback image.
- Both tracks keep the original green-screen master; the page background always comes from CSS or the page composite layer.

## Route to the Follow-on Workflow

- `alpha-atlas`: read [minimax-spritesheet.en.md](minimax-spritesheet.en.md).
- `chroma-video`: read [chroma-video.en.md](chroma-video.en.md).
