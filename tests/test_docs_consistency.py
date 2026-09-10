from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]


def read(relative: str) -> str:
    # 文档按行宽换行，断言基于去掉换行后的连续文本
    return (ROOT / relative).read_text(encoding="utf-8").replace("\n", "")


def bash_blocks(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    return re.findall(r"^```bash\n(.*?)^```", source, re.S | re.M)


def files_with_bash(snippet: str) -> list[str]:
    return sorted(
        path.name
        for path in DOC_PATHS
        if any(snippet in block for block in bash_blocks(path))
    )


class DocsConsistencyTests(unittest.TestCase):
    """文档架构回归：唯一事实源、链接有效、关键语义与脚本能力。

    每个语义只在它的事实源文件中断言一次，不依赖跨文件重复的固定句。
    """

    # ---------- SKILL.md：主流程与关键防回归语义 ----------

    def test_skill_defines_concept_contract_gate(self) -> None:
        skill = read("SKILL.md")
        self.assertIn("Concept Contract", skill)
        self.assertIn("subject_count", skill)
        self.assertIn("background_owner", skill)
        self.assertIn("input_semantics", skill)
        self.assertIn("time_control", skill)
        self.assertIn("navigation", skill)
        self.assertIn("clip_continuity", skill)
        self.assertIn("不改写、不扩写", skill)

    def test_key_anti_regression_semantics_have_canonical_homes(self) -> None:
        skill = read("SKILL.md")
        qa = read("references/qa.md")
        chroma = read("references/chroma-video.md")
        # 场景背景默认与视频一起生成（baked 默认）
        self.assertIn("baked-video", skill)
        self.assertIn("background_owner: video", skill)
        # 只有明确透明复用才用 chroma
        self.assertIn("主体必须透明复用在页面背景", skill)
        # 多段同脸与实际尾帧接力
        self.assertIn("同脸", qa)
        self.assertIn("实际尾帧", qa)
        # Pilot 通过后才量产
        self.assertIn("Pilot 硬门", qa)
        self.assertIn("approve-pilot", qa)
        # 坏绿幕直接拒收
        self.assertIn("拒收母版", chroma)

    def test_motion_brief_does_not_duplicate_contract_fields(self) -> None:
        source = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        section = source.split("建立生产计划", 1)[1].split("### 3.", 1)[0]
        block = re.search(r"```yaml\n(.*?)```", section, re.S)
        self.assertIsNotNone(block, "Motion Brief 缺少 yaml 模板")
        brief = block.group(1)
        top_level_fields = set(re.findall(r"^([a-z_]+):", brief, re.M))
        for field in (
            "subject_count",
            "background_owner",
            "clip_continuity",
            "driver",
            "input_semantics",
            "time_control",
            "navigation",
            "scene",
            "destination",
        ):
            self.assertNotIn(
                field, top_level_fields, f"Motion Brief 复制了合同字段 {field}"
            )

    def test_skill_stays_within_line_budget(self) -> None:
        lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 200)

    def test_skill_has_no_parallel_principles_flow(self) -> None:
        source = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("## 核心原则", source)
        self.assertEqual(source.count("## 主流程"), 1)

    def test_skill_separates_input_navigation_and_time_control(self) -> None:
        skill = read("SKILL.md")
        runtime = read("references/runtime.md")
        self.assertIn("格式选择与播放方式是两件事", skill)
        self.assertIn("分页页面也可以使用连续时间轴", skill)
        self.assertIn("滚动既可以 scrub，也可以触发片段播放", runtime)
        self.assertIn("start <= hold < endExclusive", runtime)
        self.assertIn("one-gesture-one-step", runtime)
        self.assertIn("programmatic_navigation=ignore", runtime)
        self.assertIn("timeline.json.states[].id", runtime)

    def test_skill_no_longer_mandates_chroma_for_everything(self) -> None:
        skill = read("SKILL.md")
        self.assertNotIn("固定绿幕管线", skill)
        self.assertNotIn("不存在“直接生成最终场景背景”的分支", skill)
        # 旧 Motion Brief 无条件要求 matte，新模板按背景归属分路线
        self.assertNotIn("matte_delivery: required", skill)

    def test_skill_routes_to_every_reference(self) -> None:
        skill = read("SKILL.md")
        for ref in sorted((ROOT / "references").glob("*.md")):
            self.assertIn(
                f"references/{ref.name}", skill, f"SKILL.md 没有路由到 {ref.name}"
            )

    # ---------- 唯一事实源：命令示例只存在于一个 canonical reference ----------

    def test_command_examples_have_single_canonical_home(self) -> None:
        expectations = {
            "motion_budget.py": ["delivery-selection.md"],
            "video_job.py": ["prompting.md"],
            "compose_travel_frames.py": ["prompting.md"],
            "approve-pilot": ["qa.md"],
            "verify-chain": ["qa.md"],
            "compile_scroll_video.py": ["baked-video.md", "chroma-video.md"],
            "optimize_motion.py": ["optimization.md"],
            "loop_cleanup.py": ["minimax-spritesheet.md"],
            "motion_pipeline.py": ["minimax-spritesheet.md"],
            "create_explainer.py": ["explainer.md"],
            "oil_motion_config.py": [],  # 原终端入口不再作为默认命令示例
        }
        for snippet, expected in expectations.items():
            self.assertEqual(
                files_with_bash(snippet),
                expected,
                f"{snippet} 的命令示例不在唯一事实源 {expected}",
            )

    def test_page_setup_and_real_video_submission_share_profile(self) -> None:
        skill = read("SKILL.md")
        self.assertIn("profile.ts\" setup default", skill)
        self.assertIn("profile.ts\" status default", skill)
        self.assertIn("profile.ts\" run default -- python3", read("references/prompting.md"))

    def test_canonical_sections_not_duplicated(self) -> None:
        docs = {path.name: path.read_text(encoding="utf-8") for path in DOC_PATHS}
        for marker, home in (
            ("固定决策顺序", "delivery-selection.md"),
            ("逐帧模拟运行时抠色", "chroma-video.md"),
            ("postEncodeKeyingPassed", "chroma-video.md"),
            ("扩大抠色阈值", "chroma-video.md"),
            ("真实页面最终位置挂载", "qa.md"),
            ("不接受“差不多”", "qa.md"),
            ("不允许误差逐段累积", "qa.md"),
            ("接口错误 `2013`", "prompting.md"),
        ):
            homes = sorted(name for name, text in docs.items() if marker in text)
            self.assertEqual(homes, [home], f"{marker} 应只属于 {home}")

    def test_no_exact_duplicate_prose_paragraphs(self) -> None:
        seen: dict[str, str] = {}
        for path in DOC_PATHS:
            source = path.read_text(encoding="utf-8")
            for paragraph in re.split(r"\n\s*\n", source):
                normalized = re.sub(r"\s+", " ", paragraph).strip()
                if len(normalized) < 120:
                    continue
                previous = seen.get(normalized)
                self.assertIsNone(
                    previous,
                    f"{path.name} 与 {previous} 存在完全重复段落",
                )
                seen[normalized] = path.name

    # ---------- 职责边界：各文档不复述其他事实源的段落 ----------

    def test_prompting_keeps_params_but_not_gate_algorithms(self) -> None:
        doc = read("references/prompting.md")
        # 提交参数是 prompting 的职责
        self.assertIn("--loop-frame", doc)
        self.assertIn("--seed", doc)
        self.assertIn("--continuity-mode chain", doc)
        # 公共工作流与 Pilot/帧链算法不复述，只链接
        self.assertNotIn("固定工作流", doc)
        self.assertNotIn("在联网前阻断", doc)
        self.assertNotIn("SHA-256 完全一致", doc)

    def test_minimax_keeps_only_atlas_specifics(self) -> None:
        doc = read("references/minimax-spritesheet.md")
        # 图集路线专属命令仍在
        self.assertIn("loop_cleanup.py", doc)
        self.assertIn("atlas", doc)
        # 首尾模式表与公共提交/验收复述已删除
        self.assertNotIn("仅参考生成", doc)
        self.assertNotIn("母版门槛", doc)
        self.assertNotIn("video_job.py", doc)
        # 公共步骤只链接，不复述清单
        self.assertNotIn("完整观看视频", doc)

    def test_skill_flow_steps_link_instead_of_repeating(self) -> None:
        skill = read("SKILL.md")
        # Pilot 四项清单、帧链算法、抠色算法只存在于 qa / chroma-video
        self.assertNotIn("真实页面最终位置挂载", skill)
        self.assertNotIn("qa/frame-chain.json` 证明", skill)
        self.assertNotIn("similarity", skill)
        self.assertNotIn("smoothDamp", skill)
        self.assertNotIn("同脸、同发型", skill)
        self.assertNotIn("拒收母版", skill)
        self.assertNotIn("SHA-256 完全一致", skill)
        self.assertNotIn("48 FPS", skill)

    # ---------- 链接有效 ----------

    def test_markdown_links_resolve(self) -> None:
        for path in DOC_PATHS:
            source = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", source):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target = target.split("#", 1)[0]
                resolved = (path.parent / target).resolve()
                self.assertTrue(
                    resolved.exists(), f"{path.name} 的链接失效: {target}"
                )

    def test_no_reference_is_orphaned(self) -> None:
        for ref in sorted((ROOT / "references").glob("*.md")):
            others = "\n".join(
                path.read_text(encoding="utf-8")
                for path in DOC_PATHS
                if path != ref
            )
            self.assertIn(ref.name, others, f"{ref.name} 没有被任何文档链接")

    # ---------- 各 canonical reference 的关键语义 ----------

    def test_delivery_selection_owns_route_selection(self) -> None:
        doc = read("references/delivery-selection.md")
        self.assertIn("baked-video", doc)
        self.assertIn("--background-owner", doc)
        self.assertIn("delivery.selected", doc)
        self.assertIn("固定决策顺序", doc)
        self.assertIn("runtime.controller", doc)

    def test_chroma_route_owns_reject_first_matte_gate(self) -> None:
        doc = read("references/chroma-video.md")
        self.assertIn("逐帧模拟运行时抠色", doc)
        self.assertIn("runtime.keying", doc)
        self.assertIn("溢色", doc)
        self.assertIn("拒收", doc)
        self.assertIn("禁止靠扩大抠色阈值", doc)
        self.assertIn("background-matrix", doc)

    def test_baked_route_reference(self) -> None:
        doc = read("references/baked-video.md")
        self.assertIn("background_owner: video", doc)
        self.assertIn("不做抠色", doc)

    def test_prompting_owns_submission_and_prompt_sections(self) -> None:
        doc = read("references/prompting.md")
        self.assertIn("Concept Contract", doc)
        self.assertIn("Identity Bible", doc)
        self.assertIn("场景背景段（baked 路线）", doc)
        self.assertIn("视频色键段（仅 chroma 路线）", doc)
        self.assertIn("直接生成真实透明背景 PNG", doc)
        self.assertIn("composite_alpha_keyframe.py", doc)
        self.assertIn("--stage", doc)
        self.assertIn("--continuity-mode chain", doc)

    def test_qa_owns_gates_and_acceptance(self) -> None:
        doc = read("references/qa.md")
        self.assertIn("Concept Contract 回归", doc)
        self.assertIn("Identity Bible", doc)
        self.assertIn("连续帧链", doc)
        self.assertIn("Pilot 硬门", doc)
        self.assertIn("frame-chain.json", doc)
        self.assertIn("pilot/approval.json", doc)
        self.assertIn("verify-output-chain", doc)

    # ---------- 脚本能力与文档一致 ----------

    def test_production_gates_are_executable(self) -> None:
        qa = read("references/qa.md")
        script = read("scripts/production_gate.py")
        video_job = read("scripts/video_job.py")
        budget = read("scripts/motion_budget.py")
        compiler = read("scripts/compile_scroll_video.py")
        self.assertIn("pilot/approval.json", qa)
        self.assertIn("qa/frame-chain.json", qa)
        self.assertIn("approve-pilot", script)
        self.assertIn("verify-chain", script)
        self.assertIn("verify-output-chain", script)
        self.assertIn("contract_continuity_mode", script)
        self.assertIn("--stage", video_job)
        self.assertIn("validate_pilot_approval", video_job)
        self.assertIn("--background-owner", budget)
        self.assertIn("--background-owner", compiler)
        self.assertIn("postEncodeKeyingReport", compiler)
        self.assertIn("checkedFrames", compiler)

    def test_runtime_assets_cover_both_time_control_modes(self) -> None:
        interactive = read("assets/interactive-motion.ts")
        chroma = read("assets/chroma-video-renderer.ts")
        gesture = read("assets/step-gesture.ts")
        self.assertIn("createFrameAnimator", interactive)
        self.assertIn("createSegmentPlayer", interactive)
        self.assertIn("start <= hold < endExclusive", interactive)
        self.assertNotIn("timeupdate", interactive)
        self.assertIn("startLive", chroma)
        self.assertIn("stopLive", chroma)
        self.assertIn("createStepGestureAdapter", gesture)
        self.assertIn("setProgrammaticNavigation", gesture)

    def test_command_examples_do_not_omit_hard_gate_arguments(self) -> None:
        for path in DOC_PATHS:
            for block in bash_blocks(path):
                if "motion_budget.py" in block:
                    self.assertIn(
                        "--background-owner",
                        block,
                        f"{path.name} 的预算命令漏传背景归属",
                    )
                    self.assertIn(
                        "--time-control",
                        block,
                        f"{path.name} 的预算命令漏传时间控制",
                    )
                if "compile_scroll_video.py" in block:
                    self.assertIn(
                        "--background-owner",
                        block,
                        f"{path.name} 的编译命令漏传背景归属",
                    )
                    self.assertIn(
                        "--frame-policy",
                        block,
                        f"{path.name} 的编译命令漏传帧策略",
                    )
                    self.assertIn(
                        "--timeline-output",
                        block,
                        f"{path.name} 的编译命令漏传时间轴输出",
                    )
                if "video_job.py" in block:
                    self.assertIn(
                        "--stage",
                        block,
                        f"{path.name} 的生成命令漏传 Pilot/production 阶段",
                    )

    # ---------- evals 覆盖关键场景 ----------

    def test_evals_cover_single_anime_baked_case(self) -> None:
        evals = json.loads(read("evals/evals.json"))["evals"]
        prompts = [item["prompt"] for item in evals]
        expected = [item["expected_output"] for item in evals]
        self.assertTrue(
            any("单人" in p and "动漫" in p for p in prompts),
            "evals 必须包含单人动漫场景用例",
        )
        self.assertTrue(
            any("Concept Contract" in e and "baked-video" in e for e in expected),
            "evals 必须断言 Concept Contract 与 baked-video 路线",
        )
        self.assertTrue(
            any("拒绝" in e and "阈值" in e for e in expected),
            "evals 必须断言禁止用调阈值掩盖抠色缺陷",
        )


if __name__ == "__main__":
    unittest.main()
