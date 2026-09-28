---
name: oil-motion
description: "把 AI 生成或已有的视频、序列帧变成随滚动、指针、拖动、触摸、设备方向、音频、数据或状态变化的网页动画：设计动作方向，生成关键帧与视频，整理成图集或视频，编译时间轴并接入运行时。用户需要角色转向、产品拆解、镜头穿越、一镜到底转场，或要清理、抠色、补帧、压缩绿幕视频与雪碧图时使用。不用于纯 CSS、JS、SVG、Lottie 或实时 3D 就能完成的界面过渡与微交互（交给普通前端实现），也不用于独立成片剪辑、单张配图或静态页面。"
---

# Oil Motion

把用户的交互意图转换为可验收的动画素材、时间轴清单和网页运行时。AI 生成负责肢体、结构、材质、遮挡等语义变化；程序负责输入映射、播放控制、媒体处理和性能。

确定性流水线需要 Python 3.10+、Pillow、ffmpeg 和 ffprobe：

```bash
OIL_MOTION="<当前 SKILL.md 所在的绝对目录>"
python3 -m pip install -r "$OIL_MOTION/scripts/requirements.txt"
```

关键帧与视频默认通过 ZenMux 生成，模型写在 `image_job.py` 与 `video_job.py` 中；只有模型无法完成目标或用户明确指定时才更换。已有视频或序列帧时从分析开始，不调用生成服务。

## 首次配置

第一次调用生成服务前检查凭据；纯本地处理不需要 Key：

```bash
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" status default
node "$OIL_MOTION/scripts/credential-ui/src/profile.ts" setup default
```

退出码 0 直接继续；2 表示缺失，此时运行 `setup` 并把返回的本机链接交给用户亲自填写。所有生成命令都通过 `profile.ts run default --` 执行。依赖安装、退出码含义和安全边界见 [references/api-key-setup.md](references/api-key-setup.md)。

## 四个唯一事实源

每项信息只保存在一个位置，其他文件引用它，不复制：

1. `source/concept-contract.yaml`：用户明确要求的对象、视觉、交互和连续性。
2. `source/motion-brief.yaml`：由合同派生的关键帧、片段和生产计划。
3. `build/timeline.json`：成片的实际帧率、段落边界、停帧和播放曲线。
4. `build/motion-budget.json`：交付格式与运行时控制器的自动选择结果。

## 主流程

### 1. 锁定用户意图

用户只有模糊目标时，先读 [references/concepts.md](references/concepts.md)，给出最多三个真正不同的方向；要求已经明确时直接写 Concept Contract。

需要外部案例启发时，按表达目的选读 [references/motion-patterns.md](references/motion-patterns.md)。先分清哪些变化属于素材本身、哪些只是容器编排或 UI 状态，只有前者进入生成流程。

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
aspect_ratio: 16:9 | 9:16 | 1:1 | 21:9 | custom
destination: <页面位置、最大显示尺寸和目标设备>
```

判断规则：

- `aspect_ratio` 取自 `destination` 的真实容器：横向全屏或 Hero 通常是 `16:9`，竖屏全屏是 `9:16`，卡片、头像等方形视窗是 `1:1`；不要未经确认就默认 `1:1`。容器比例与生成比例不一致时，在合同中写明裁切或补边策略。锁定后关键帧尺寸、视频画幅和编译输出都沿用同一比例，尺寸对照见 [references/prompting.md](references/prompting.md)。
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
pixel_dimensions: <宽x高，由合同的 aspect_ratio 与 DPR 派生>
reduced_motion: <静态替代状态>
```

`parameter_space` 描述素材时间轴，不描述页面布局：`linear` 是有起止的时间轴，`circular` 是闭环，`2d` 是二维采样，`discrete` 是互不连续的状态。不要把二维或无序状态压成一条线性视频。

`frame_policy` 与 `target_fps` 的取舍标准见 [references/optimization.md](references/optimization.md)。

整组位移、缩放、旋转、裁切和时间映射由程序完成；关节、结构、材质、接触和遮挡变化由生成模型完成。如果只移动整张图不能保持自然，就生成完整动作，不继续叠加 CSS 补丁。

### 3. 自动选择交付与运行时

生成任何素材前，用 Brief 中的计划帧数、显示尺寸和参数空间运行 `motion_budget.py --strict`，显式传入合同中的 `background_owner` 和 `time_control`，保存 `build/motion-budget.json`。Pilot 按这个结果挂载到真实页面；之后帧数或尺寸变化就重新预算。脚本分别返回：

- `delivery.selected`：`baked-video | chroma-video | alpha-atlas`。
- `runtime.controller`：`frame-scrub | segment-playback | autonomous-playback`。

格式选择与播放方式是两件事，不得互相推断。命令和决策顺序见 [references/delivery-selection.md](references/delivery-selection.md)。按结果只读取一条媒体路线：

- `alpha-atlas`：[references/alpha-atlas.md](references/alpha-atlas.md)
- `chroma-video`：[references/chroma-video.md](references/chroma-video.md)
- `baked-video`：[references/baked-video.md](references/baked-video.md)

### 4. 制作关键帧

1. 有角色或需要身份一致时，先写 Identity Bible。
2. 生成并验收 `K0…Kn`；每段只承担一个主要语义变化，片段 `i` 使用 `Ki → Ki+1`。`clip_continuity: chain` 时，第 2 段起的首帧改用上一段验收后的实际尾帧，尾帧仍是计划关键帧。
3. 用 `image_job.py` 生成关键帧：按 `aspect_ratio` 传尺寸，并核对脚本报告的实际宽高比；尺寸至少覆盖最大 CSS 尺寸乘目标 DPR。真实产品、既定角色或上一张关键帧用 `--image` 作为参考输入，不只凭文字描述。
4. `background_owner: page` 传 `--background transparent`，脚本会拒收没有真实 Alpha 的结果；不得先生成色底再反向抠图。视频模型需要色键输入时，由 `composite_alpha_keyframe.py` 从透明源合成副本。`background_owner: video` 传 `--background opaque`，场景直接画进关键帧。
5. 命令、尺寸对照、提示词、首尾帧模式和提交方式见 [references/prompting.md](references/prompting.md)。宿主自带的图片工具同样能输出真实 Alpha 并接受参考图时也可以使用，验收标准不变。已有视频或序列帧时跳过生成，保留原始素材并从分析开始。

### 5. 先做 Pilot

批量生成前，只完成第一组关键帧、第一段视频，并按已选路线挂载到真实页面。按 [references/qa.md](references/qa.md) 通过 Pilot 硬门后才能量产；失败就修正上游，不在运行时掩盖。

### 6. 生成并逐段验收

按 [references/prompting.md](references/prompting.md) 生成母版，按 [references/qa.md](references/qa.md) 验收内容与连续帧链。`chain` 模式必须同时验证生成输入接力和相邻成片解码后的输出接缝；任一失败都停止后续生产。

### 7. 帧准备、清理与编译时间轴

按 [references/optimization.md](references/optimization.md) 执行 `frame_policy`（插帧出现重影或伪影时退回 `native` 或重新生成），再按已选媒体路线清理和编译。所有裁剪和拼接都要检查新产生的相邻帧；不得用一次远距离跳帧替代缓慢尾部变化。

编译后生成 `build/timeline.json`，字段语义只以 [references/runtime.md](references/runtime.md) 的时间轴规范为准。时间值必须由最终编译结果生成，不手工抄写。

### 8. 接入运行时

从 [assets/interactive-motion.ts](assets/interactive-motion.ts) 的对应控制器开始实现（`frame-scrub` 管理随动与最短环形距离，`segment-playback` 管理分段与反向）；分步手势使用 [assets/step-gesture.ts](assets/step-gesture.ts)。输入映射、分段播放、反向、取消、预加载和降级只以 [references/runtime.md](references/runtime.md) 为准。

### 9. 最终验收

按 [references/qa.md](references/qa.md) 在目标 CSS 尺寸、DPR、冷缓存、快速反向、移动端和资源失败条件下验收。页面导航、时间控制、媒体格式和连续性分别检查，不用一种检查代替另一种。

需要动画原理展示页时，读 [references/explainer.md](references/explainer.md) 并使用 `create_explainer.py`。

## 交付

保留 `source/`、`pilot/`、`build/`、`qa/` 和 `final/`。`final/` 只包含选中的主资源、静态降级和运行时入口；同时交付四个事实源及可复现的处理命令。
