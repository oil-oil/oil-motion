---
name: oil-motion
description: "Design, implement, optimize, and explain interactive web animations driven by scroll, pointer, drag, touch, device orientation, audio, data, or component state. Use when a webpage needs responsive visual motion for products, interfaces, diagrams, characters, or scene transitions."
---

# Oil Motion

把用户的交互意图转换为可验收的动画素材、时间轴清单和网页运行时。AI 生成负责肢体、结构、材质、遮挡等语义变化；程序负责输入映射、播放控制、媒体处理和性能。

确定性流水线需要 Python 3、Pillow、ffmpeg 和 ffprobe：

```bash
OIL_MOTION="$HOME/.codex/skills/oil-motion"
python3 -m pip install -r "$OIL_MOTION/scripts/requirements.txt"
```

默认视频模型为 ZenMux `minimax/minimax-h3`。只有模型无法完成目标或用户明确指定时才更换。
也可通过 `--provider orcarouter` 走 [OrcaRouter](https://www.orcarouter.ai) 网关调用同一个模型。

## 首次配置

生成视频前检查一次；已配置则直接继续：

```bash
python3 "$OIL_MOTION/scripts/oil_motion_config.py" status
python3 "$OIL_MOTION/scripts/oil_motion_config.py" set
```

需要走 OrcaRouter 网关时，改用 `set --provider orcarouter`（密钥优先读
`ORCAROUTER_API_KEY` 环境变量）。

密钥保存在 `~/.config/oil-motion/config.json`。不得写入项目、提示词、命令参数、日志或任务元数据。

## 四个唯一事实源

每项信息只保存在一个位置，其他文件引用它，不复制：

1. `source/concept-contract.yaml`：用户明确要求的对象、视觉、交互和连续性。
2. `source/motion-brief.yaml`：由合同派生的关键帧、片段和生产计划。
3. `build/timeline.json`：成片的实际帧率、段落边界、停帧和播放曲线。
4. `build/motion-budget.json`：交付格式与运行时控制器的自动选择结果。

## 主流程

### 1. 锁定用户意图

用户只有模糊目标时，先读 [references/concepts.md](references/concepts.md)，给出最多三个真正不同的方向；要求已经明确时直接写 Concept Contract。

```yaml
subject_count: <number>
subjects:
  - identity: <可验证的身份或外观锚点>
style: <用户原词>
motion_intent: <动作及视觉结果>
background_owner: video | page
scene: <背景属于视频时的场景、镜头和光线要求>
driver: scroll | pointer | drag | touch | orientation | audio | data | state | time
input_semantics: continuous | step | event
time_control: scrub | segment-play | autonomous
navigation: continuous | paged | none
clip_continuity: chain | independent
continuity: [<必须保持不变或连续的内容>]
destination: <页面位置、最大显示尺寸和目标设备>
```

判断规则：

- `scrub`：输入值与时间轴位置持续对应，输入停止时画面停在当前位置。
- `segment-play`：输入选择下一状态，片段随后按时间播放；反向输入应从当前画面撤回，不得换源硬切。
- `autonomous`：动画由时间推进，交互只负责开始、暂停或切换状态。
- `navigation` 只描述页面如何移动，不决定视频如何播放；分页页面也可以使用连续时间轴。
- 镜头、环境光、接触阴影、景深或背景连续性重要时使用 `background_owner: video`。只有主体必须透明复用在页面背景上时使用 `page`。
- 用户已说清的内容直接记录，不改写、不扩写。缺项会改变可生成性、可验收结果或生产路线时，必须先补齐。

### 2. 建立生产计划

Motion Brief 只保存派生计划，不复制合同字段：

```yaml
concept_contract: source/concept-contract.yaml
identity_bible: source/identity-bible.md | null
parameter_space: linear | circular | 2d | discrete
media_access: sequential | random
gesture_policy:
  unit: continuous | one-gesture-one-step
  inertia: coalesce | preserve
  while_active: retarget | queue | ignore
  boundary: clamp | loop
  programmatic_navigation: ignore | observe
storyboard: <有序视觉阶段>
keyframes: <K0…Kn>
clip_chain: <每段使用的相邻关键帧>
rest_state: <初始及失去输入时的状态>
loop: open | closed | none
anchor: fixed-body | center | bottom | free
scene_continuity: <仅背景属于视频时填写>
frame_policy: native | interpolate
target_fps: <由源素材和运行时需求决定>
quality_target: <分辨率、DPR 和文件预算>
reduced_motion: <静态替代状态>
```

`parameter_space` 描述素材时间轴，不描述页面布局：`linear` 是有起止的时间轴，`circular` 是闭环，`2d` 是二维采样，`discrete` 是互不连续的状态。不要把二维或无序状态压成一条线性视频。

整组位移、缩放、旋转、裁切和时间映射由程序完成；关节、结构、材质、接触和遮挡变化由生成模型完成。如果只移动整张图不能保持自然，就生成完整动作，不继续叠加 CSS 补丁。

### 3. 制作关键帧

1. 有角色或需要身份一致时，先写 Identity Bible。
2. 生成并验收 `K0…Kn`；每段只承担一个主要语义变化，片段 `i` 使用 `Ki → Ki+1`。
3. 关键帧至少覆盖最大 CSS 尺寸乘目标 DPR，按最终裁切验收。
4. `background_owner: page` 时，使用 `$imagegen` 直接生成真实 Alpha PNG；不得先生成色底再反向抠图。视频模型需要色键输入时，再由 `composite_alpha_keyframe.py` 从透明源合成副本。
5. 提示词、首尾帧模式和提交方式见 [references/prompting.md](references/prompting.md)。已有视频或序列帧时跳过生成，保留原始素材并从分析开始。

### 4. 先做 Pilot

批量生成前，只完成第一组关键帧、第一段视频和真实页面挂载。按 [references/qa.md](references/qa.md) 通过 Pilot 硬门后才能量产；失败就修正上游，不在运行时掩盖。

### 5. 自动选择交付与运行时

运行 `motion_budget.py --strict`，显式传入合同中的 `background_owner` 和 `time_control`，保存 `build/motion-budget.json`。脚本分别返回：

- `delivery.selected`：`baked-video | chroma-video | alpha-atlas`。
- `runtime.controller`：`frame-scrub | segment-playback | autonomous-playback`。

格式选择与播放方式是两件事，不得互相推断。命令和决策顺序见 [references/delivery-selection.md](references/delivery-selection.md)。按结果只读取一条媒体路线：

- `alpha-atlas`：[references/minimax-spritesheet.md](references/minimax-spritesheet.md)
- `chroma-video`：[references/chroma-video.md](references/chroma-video.md)
- `baked-video`：[references/baked-video.md](references/baked-video.md)

### 6. 生成并逐段验收

按 [references/prompting.md](references/prompting.md) 生成母版，按 [references/qa.md](references/qa.md) 验收内容与连续帧链。`chain` 模式必须同时验证生成输入接力和相邻成片解码后的输出接缝；任一失败都停止后续生产。

### 7. 清理、编译并生成时间轴

按 [references/optimization.md](references/optimization.md) 执行 `frame_policy`，再进入已选择的媒体路线。所有裁剪和拼接都要检查新产生的相邻帧；不得用一次远距离跳帧替代缓慢尾部变化。

编译后生成 `build/timeline.json`，字段语义只以 [references/runtime.md](references/runtime.md) 的时间轴规范为准。时间值必须由最终编译结果生成，不手工抄写。

### 8. 接入运行时

从 [assets/interactive-motion.ts](assets/interactive-motion.ts) 的对应控制器开始实现；分步手势使用 [assets/step-gesture.ts](assets/step-gesture.ts)。输入映射、分段播放、反向、取消、预加载和降级只以 [references/runtime.md](references/runtime.md) 为准。

### 9. 最终验收

按 [references/qa.md](references/qa.md) 在目标 CSS 尺寸、DPR、冷缓存、快速反向、移动端和资源失败条件下验收。页面导航、时间控制、媒体格式和连续性分别检查，不用一种检查代替另一种。

需要动画原理展示页时，读 [references/explainer.md](references/explainer.md) 并使用 `create_explainer.py`。

## 交付

保留 `source/`、`pilot/`、`build/`、`qa/` 和 `final/`。`final/` 只包含选中的主资源、静态降级和运行时入口；同时交付四个事实源及可复现的处理命令。
