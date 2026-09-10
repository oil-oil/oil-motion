# AI 视频动作提示词与任务提交

本文档是提示词写法与 `video_job.py` 提交命令的唯一事实源。路线选择见
[delivery-selection.md](delivery-selection.md)，Pilot 与帧链硬门命令见
[qa.md](qa.md)。

## 准备首尾帧

生产主流程（先生图、再生视频、逐段串联）见 SKILL.md 主流程；本节只覆盖提示词侧的
首尾帧准备。视频提示词只描述两张已验收关键帧之间如何连续变化，不再承担终点设计；
主体身份、产品结构、Logo、构图和风格必须先在关键帧图片中解决。

`background_owner=page` 时，关键帧图片使用内置 `$imagegen` 直接生成真实透明背景 PNG，
保留原始 Alpha；不要让生图模型生成绿色、品红、灰色、白色或棋盘格背景。提交视频前，
再从透明源确定性合成视频模型需要的均匀色键副本：

```bash
python3 "$OIL_MOTION/scripts/composite_alpha_keyframe.py" \
  source/K0-alpha.png source/K0-video.png \
  --key-color '#00FF00'
```

透明源与视频输入副本必须分开保存。主体含大量绿色时，合成副本改用 `#FF00FF`。

需要同一主体从轨道一端精确移动到另一端时，可以先准备透明主体层，用程序生成身份和尺寸
完全一致的首尾帧，再交给视频模型补全中间形变：

```bash
python3 "$OIL_MOTION/scripts/compose_travel_frames.py" subject.png \
  --first-output first-green.png \
  --last-output last-green.png \
  --size 864x1536 \
  --subject-height 0.36 \
  --subject-anchor-x 0.535
```

该工具只负责扁平轨道、缩放和精确位移。中间的结构形变、接触关系和前后遮挡仍由首尾帧
约束下的视频模型完成。

## 写提示词前先决定

提示词从 Concept Contract 和 Identity Bible 出发，不得加入用户未确认的主体、人数、
风格、情绪或叙事形式；合同中的限制必须原样成为提示词约束。

先写清楚：

1. `time_control` 是逐帧 scrub、分段播放还是自主播放。
2. 时间轴或状态转场的起点、终点和方向。
3. 主体哪些部分允许变化，哪些必须固定（角色照抄 Identity Bible 的身份锚点）。
4. 是否闭环。
5. 背景归属：`background_owner=video` 时写明场景、环境光、地面接触和景深如何保持
   连续；`background_owner=page` 时写明关键帧生图使用真实 Alpha、视频输入副本使用
   绿色还是洋红色键，以及如何保证视频四角与时间维度均匀。
6. 最终会按时间、角度、二维位置还是状态取帧。

图片模型负责关键帧并直接输出透明通道；视频模型负责动作语义和画面连续性，不负责精确
切帧、Alpha 视频、帧编号、压缩或图集。不要让视频提示词承担透明通道或图集输出。

## 画幅比例与分辨率映射

生图与视频模型的分辨率必须由 `concept-contract.yaml` 的 `aspect_ratio` 决定，不可盲目使用默认尺寸：

| 目标场景 | 比例 (`aspect_ratio`) | 图片模型推荐尺寸 (`image_job.py --size`) | 视频模型行为 (`video_job.py`) | 编译目标 |
| :--- | :--- | :--- | :--- | :--- |
| **桌面全屏 / 沉浸式 Hero / 宽幅转场** | `16:9` | `1792x1024`（或按需缩放到 `1280x720` / `1920x1080`） | 自动推断为 `16:9`，生成宽屏过渡 | `1920x1080` All-Intra |
| **移动端全屏 / 短视频 / 竖屏故事** | `9:16` | `1024x1792`（或 `720x1280` / `1080x1920`） | 自动推断为 `9:16`，生成竖屏过渡 | `1080x1920` All-Intra |
| **局部微交互 / 头像 / 独立方形视窗** | `1:1` | `1024x1024` | 自动推断为 `1:1`，生成方形过渡 | `1080x1080` All-Intra |
| **宽银幕全景叙事** | `21:9` | `1792x768`（裁剪或缩放） | 自动推断为 `21:9` | `2560x1080` All-Intra |

**核心禁令**：严禁在未确认宿主容器的情况下直接生成 `1:1` 方图充当全屏桌面内容，否则会导致严重的左右黑屏或上下 40% 暴力裁切。

## 提交视频任务（video_job.py）

`video_job.py` 用于提交、轮询和下载 ZenMux / MiniMax 原生视频任务，把重复的接口
调用、图片编码、状态轮询和结果保存程序化。提交前按 SKILL.md 的“首次配置 API Key”
检查一次即可；脚本优先读取 `ZENMUX_API_KEY`，没有环境变量时读取本地配置。

模式与参数约束：

- `reference_image` 与 `first_frame` / `last_frame` / `loop_frame` 互斥。混用会触发
  MiniMax 接口错误 `2013`，脚本会在联网前阻止提交。
- 首尾帧转场需要锁定身份时，先把身份和风格生成进验收后的首尾关键帧，不能再附加
  `reference_image`。
- 闭环动作把同一张已验收构图同时传为首帧和尾帧（`--loop-frame`）。这能加强接缝
  约束，但仍需检查首尾差异和运动方向。
- 默认不传 `--model`（固定 `minimax/minimax-h3-max`）和 `--ratio`（按首帧推断画幅）。
- 默认传 5 秒 `duration`。使用 `--frames` 时不传 `duration`，二者不能同时出现；
  只有当前接口明确支持帧数控制时才使用 `--frames`。
- 模型支持时用 `--seed` 复现，并保存任务元数据和尾帧；seed 不能替代参考图和首尾帧。
- `generate_audio=false` 不能作为最终无音轨保证；网页编译阶段始终显式使用 `-an`。
- 模型实际输出时长和帧数可能略高于请求，并可能在尾帧产生停顿。必须先 `probe`，
  再按目标尾帧清理，不能假设请求值就是成片值。
- 模型或接口拒绝参数时停止并报告具体响应；只有用户同意降级后，才能移除约束或更换
  模型，不要静默删掉首尾帧。
- 一条视频只承担一条连续时间轴或一个状态转场；单段动作默认 3–6 秒，长序列更容易漂移。
- `--stage` 必填：第一段为 `pilot`，后续生产段为 `production` 并传
  `--pilot-approval`；连续叙事的生产段同时传 `--continuity-mode chain`、
  `--previous-tail` 和 `--frame-chain-manifest`。Pilot 批准与帧链校验的规则、
  阻断条件和命令见 [qa.md](qa.md)。

第一段 Pilot（闭环）：

```bash
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" run default -- python3 "$OIL_MOTION/scripts/video_job.py" \
  --stage pilot \
  --segment-index 1 \
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

单向转场把 `--loop-frame` 换成 `--last-frame source/last-frame.png`。

第 2 段及之后的连续生产：

```bash
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" run default -- python3 "$OIL_MOTION/scripts/video_job.py" \
  --stage production \
  --segment-index 2 \
  --pilot-approval pilot/approval.json \
  --continuity-mode chain \
  --previous-tail source/segment-01-last-frame.jpg \
  --frame-chain-manifest qa/frame-chain.json \
  --prompt-file source/segment-02.txt \
  --first-frame source/segment-02-first.jpg \
  --last-frame source/K2.png \
  --output source/segment-02.mp4
```

分辨率先用 `768p` 验证动作，最终清晰度不足再使用 `2K`。

## 通用身份锁定段

有角色时，先把 Identity Bible 的身份锚点（脸型五官、发型发色、服装配色、标志物、
体型比例、风格线条）写进这段，再放在动作描述前，并替换尖括号：

```text
Use the supplied first and last frames as the exact identity and design
references for <SUBJECT>. Preserve the same silhouette, anatomy, face, clothing or product
geometry, colors, line work, texture, and proportions in every frame. The
subject remains the same size and at the same anchored position throughout the
shot. Do not add, remove, duplicate, or redesign any body part, accessory,
feature, logo, control, or prop.
```

如果主体是插画，补充：

```text
Preserve the original illustration style exactly. Keep line thickness,
halftone texture, flat color regions, and edge sharpness consistent. Do not
turn the subject into volumetric CGI, photorealistic, painterly, or glossy imagery.
```

## 固定镜头段

```text
Locked camera and locked framing. No camera pan, tilt, zoom, orbit, shake,
reframing, perspective change, lens change, depth of field, or lighting change.
The body and contact point remain fixed. Only <ALLOWED_PARTS> may move.
```

只有镜头运动本身需要被滚动控制时才删除这段，并明确描述镜头轨迹。

## 场景背景段（baked 路线）

仅当 Concept Contract 锁定 `background_owner: video` 时使用。场景、环境光、地面
接触和景深就是要烧进视频的内容，必须明确锁定，保证多段之间连续：

```text
The scene is <SCENE_ANCHOR> with <LIGHTING> and <GROUND_CONTACT>. Keep the
environment, light direction, color temperature, ground contact, shadows, and
depth of field identical and continuous across the entire shot. The background
is part of the final picture: no chroma key, no flat color backdrop, no
background replacement, and no transparency.
```

多段叙事时，这一段在每条提示词中原样复用，并把上一段验收后的实际尾帧作为下一段
首帧输入。

## 视频色键段（仅 chroma 路线）

仅当 Concept Contract 锁定 `background_owner: page` 时追加到视频提示词。首尾关键帧
先由 `$imagegen` 直接生成透明 PNG，再由 `composite_alpha_keyframe.py` 合成为下方视频
输入；不要把这段用于图片生图提示词。默认 `#00FF00`，主体含绿色时改用 `#FF00FF`。

```text
The entire background is one perfectly uniform flat chroma-key <KEY_COLOR>
rectangle in every frame. No gradient, texture, noise, floor plane, horizon,
shadow, reflection, glow, particles, color variation, or lighting falloff on
the background. Keep the subject fully separated from all image borders with
generous padding. No cast shadow. No green/magenta object or reflected spill on
the subject. No text, subtitle, watermark, border, or UI.
```

模型未必严格生成指定色值，所以最重要的是四周和时间维度保持均匀。后续脚本会从边缘采样真实背景色。

## 旋转、转头与视向提示词

必须在写提示词前对照 [concepts.md](concepts.md) 的旋转物理分类，禁止混淆“时钟圆周注视”与“展台全景自转”：

### 1. 时钟圆周注视（官网头像/吉祥物 360° 鼠标跟随）

主体面部始终朝向镜头，视线在圆锥范围内随屏幕正前方顺时针圆周移动，**绝不自转露出后脑勺**：

```text
Create one continuous clockwise head and gaze rotation cycle. The face and eyes
of <SUBJECT> remain oriented toward the camera at all times; do not rotate around
to show the back of the head. An invisible target moves smoothly clockwise in a
circle on the front screen plane (12 o'clock looking up, 3 o'clock looking
right, 6 o'clock looking down, 9 o'clock looking left, returning cleanly to 12
o'clock). <SUBJECT> follows the target smoothly within a natural cone of vision,
tilting and rolling its head without leaving the front-facing half-sphere. Pass
through every intermediate angle at a constant rate without pausing or snapping.
End exactly at the first frame pose for a seamless loop. Keep torso and position
completely stationary. No blinking, idle sway, or deformation.
```

### 2. 水平有限摆头（横向 Scrub 左右巡顾，不闭环）

```text
Move once continuously from looking left (-60 degrees) through center to
looking right (+60 degrees). Do not loop, do not return to start, and do not
pause at intermediate angles. Head turns only on the horizontal yaw axis; locked
vertical pitch, locked camera, locked scale, locked center anchor.
```

### 3. 产品 360° 展台自转（电商硬件全景展示）

见后文 [产品 360° 提示词](#产品-360-提示词)，主体绕中心 Y 轴自转并展示侧面与背面。

## 影视级一镜到底连续镜头提示词

根据 [concepts.md](concepts.md) 的一镜到底洞察库，单段视频只负责一级物理转场，以首尾关键帧约束镜头连续性：

### 1. 无限尺度穿透（Powers of Ten Zoom-Through）

```text
Use the supplied first frame <MACRO_FRAME> and last frame <MICRO_FRAME> as exact
composition anchors. The camera executes one uninterrupted, accelerating forward
dolly move directly toward the center subject <TARGET>. As the camera flies
forward, the environment expands outward past the frame edges, seamlessly
magnifying scale by orders of magnitude without cuts, jump pans, or rotational
drift. Smoothly pass through intermediate layers <INTERMEDIATE_ATMOSPHERE> and
arrive precisely at the framing and alignment of the final micro frame.
```

### 2. 实体视线遮挡转场（Object Wipe / Pass-Through）

```text
Continuous uninterrupted tracking shot following <SUBJECT> through the scene. A
massive foreground obstacle <PILLAR_OR_DOORFRAME> slides rapidly across the lens
from left to right, completely occluding the frame until 100% of the screen is
filled by solid foreground tone, reaching the exact framing of the final anchor
frame. No camera jump, constant velocity, locked exposure.
```

### 3. 时光剥蚀流转（Timewarp / Weathering）

```text
Camera remains locked on the exact silhouette and perspective of <SUBJECT>. Time
accelerates through a continuous weathering transformation from the approved
first frame state <ERA_1> to the approved final frame state <ERA_2>. Materials
evolve smoothly (corrosion, oxidation, patina, or digital rebuilding) while all
structural anchors, camera distance, and perspective remain perfectly identical.
```

## 产品拆解与爆炸图

先根据真实产品参考图分别生成完整态和爆炸态图片。两张图都通过人工验收后，再作为精确首尾帧；
不要让视频模型凭文字发明最终结构。

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

爆炸方向、间距、部件数量和最终构图必须先在尾帧图片中确定。视频负责从完整态连续过渡到
该尾帧；文字标注、数字和部件高亮在生成后由程序覆盖，避免 AI 视频生成不稳定文字。

## 镜头穿越

镜头运动本身是交互内容时，不使用固定镜头段，改为明确一条可逆轨迹：

```text
Create one continuous forward camera move from <START_VIEW> to <END_VIEW>.
Follow the supplied path through <ORDERED_LANDMARKS> without cuts, orbiting,
sideways drift, speed jumps, focus pumping, or lens changes. Keep product
geometry, lighting, scale relationships, and landmark positions consistent.
Every frame must remain sharp and readable when scroll playback stops. The
reverse frame order must also form a natural backward move.
```

长距离穿越不要只给起点和终点。先生成路径上的中间关键帧，保证主体、空间地标、比例和风格
一致，再把相邻关键帧分别生成短视频。

## 多段关键帧串联

先建立 `K0 → K1 → K2…Kn`：

- `Ki` 和 `Ki+1` 是第 `i` 段视频的精确首尾帧。
- 所有关键帧复用同一组参考图、画幅、风格约束、主体比例和场景设定。
- 每段只写一个主要变化，时长通常为 3–6 秒。
- 拼接后逐帧检查接缝；若接缝不稳，重做对应短片，不重做整条时间轴。

实际尾帧接力、SHA-256 校验和误差累积处理按 [qa.md](qa.md) 的“连续帧链”执行。

## 指针二维动画

二维输入不能只靠一条左右转头视频准确表达。优先选择以下方案：

### 方案 A：角度足够

让视频生成完整方向环，运行时用 `atan2(y, x)` 映射角度。距离只影响平滑速度或回正强度，不改变姿态。

### 方案 B：二维采样

生成固定网格中的多个短片或关键姿态，例如：

```text
Generate the same subject and framing for target position <X_POSITION>,
<Y_POSITION>. Keep the exact body anchor, subject scale, lighting, style, and
background used in every other grid sample. Move only <ALLOWED_PARTS> toward
that target and settle naturally. No entrance or exit motion.
```

二维网格至少覆盖左上、上、右上、左、中、右、左下、下、右下。用程序统一锚点和尺寸，再做双线性邻域选择或插值。不要要求模型在一条视频中遍历网格后直接随机访问。

## 逐帧 scrub 时间轴

适合产品拆解、页面叙事、图表展开和场景变换：

```text
Create a single continuous transformation designed for frame-by-frame scroll
scrubbing. At frame 0, <START_STATE>. Over the shot, <ORDERED_CHANGES>. At the
last frame, <END_STATE>. Every intermediate frame must be a meaningful stable
progress state. Use constant visual continuity with no cuts, dissolves, sudden
jumps, duplicated holds, camera shake, motion blur, or unrelated motion. Keep
the composition readable when playback is stopped on any frame.
```

把多个变化写成相对进度阶段，例如 `0–35%` 完成第一阶段、`35–80%` 推进主要关系、
`80–100%` 到达最终状态。要求每个阶段持续变化，并明确禁止模型在前段快速完成主要
动作、后段只保留近重复帧。百分比用于约束节奏，不要求模型输出精确帧编号；实际节奏
仍需通过接触表检查，必要时裁剪或重定时。

scrub 序列的目标帧率由帧密度和画质验收决定。优先生成清晰的语义关键阶段，再按
[optimization.md](optimization.md) 选择保留原帧或插帧。

## 分段播放转场

适合输入触发后按时间完成、并在状态锚点停住的片段：

```text
Create one uninterrupted transition from the exact provided first frame to the
exact provided last frame. Begin the intended motion immediately, preserve all
identity, structure, framing, background, and lighting constraints throughout,
and reach the final state only at the end. No cut, dissolve, unrelated idle
motion, early completion, long final hold, or return motion.
```

每段只描述一个方向的主要变化。运行时反向通常复用同一段；只有倒放违反物理或叙事规律时，才另外生成反向片段。

## 离散状态动画

每个状态单独生成，不让一个长视频同时包含 hover、点击、成功和失败：

```text
Create a short transition from the exact neutral pose to the exact <STATE>
pose. The first frame must match the shared neutral reference exactly. Hold the
final pose only briefly. No camera movement, no unrelated idle motion, and no
return transition.
```

反向状态优先用程序倒放；只有倒放不符合物理规律时再单独生成。

## 产品 360° 提示词

```text
Use the provided product image as the exact geometry, material, color, logo,
control, and proportion reference. Rotate the product once clockwise around its
vertical center at a constant angular speed. Locked orthographic-like camera,
fixed scale, fixed center, fixed lighting, no perspective breathing, no added
details, no deformation, no text changes, no logo changes. The first and last
frames join exactly.
```

## 失败修复提示词

一次只修一个问题，同时重申所有不变量：

```text
Keep the subject identity, design, style, camera, framing, scale, anchor,
background, lighting, and correct motion unchanged. Fix only this issue:
<ONE_PRECISE_ISSUE>. Do not add any new motion or detail.
```

常见修复：

- `Keep every approved component unchanged; remove the duplicated connector.`
- `Keep the body fixed; eliminate scale pulsing and center drift.`
- `Remove the one-frame brightness flash; lighting is identical in every frame.`
- `Continue through the angle without pausing or snapping.`
- `Make the last frame match the first frame exactly for a seamless loop.`

## 拒绝过度装饰与反 AI 杂质

严禁落入常见的“AI 默认噪点”与“无脑科幻杂质”陷阱，无论用户指定何种风格，都必须剔除无意义的装饰性干扰：

1. **拒绝无端科幻元素与虚假细节堆砌**：
   - 严禁在用户未明确要求的题材中机械填入 `cyberpunk, neon glow, intricate circuitry, mechanical wires, hyperdetailed 8k, technical panels` 等套路词汇。
   - 避免满画面的细碎发光线条，这会破坏主体轮廓与画面焦点，造成廉价塑料感与视觉疲劳。
2. **拒绝表面噪点覆盖，保持视觉呼吸感**：
   - 视觉冲击力来自镜头运镜、形态对比与干净利落的画幅反差，而不是堆砌表面碎线；细节只服务于核心叙事焦点，轮廓与非焦点区域严禁装饰性杂质。
3. **负面约束补充**：
   - 针对非科幻题材必须剔除：`no unnecessary sci-fi circuitry, no generic cyberpunk neon clutter, no plastic AI noise, no over-detailed artificial lines, no visual noise.`

## 负面约束

按需要加入，不必机械复制全部：

```text
No cuts, morphing, identity drift, scale breathing, position drift, duplicated
limbs, missing limbs, extra objects, blinking, idle sway, motion blur, ghosting,
frame blending, lighting flicker, shadows on the background, camera movement,
text, watermark, border, style change, unnecessary sci-fi circuitry, or plastic AI clutter.
```

## 分辨率和时长

- 先生成 3–6 秒的单变量动作，长序列更容易漂移。
- 以最终显示尺寸的 2 倍为最低母版分辨率。
- 生成模型只负责连续动作母版；是否插帧由 Motion Brief 的 `frame_policy` 决定。
  提示词不要要求模型自行提高帧率。
