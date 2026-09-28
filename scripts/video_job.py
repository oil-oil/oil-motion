#!/usr/bin/env python3
"""提交、轮询并下载 MiniMax H3 视频任务。

密钥优先从 ZENMUX_API_KEY 读取，否则读取 Oil Motion 的本地配置。
MiniMax H3 有两种互斥的图片约束模式：

- 闭环：同一张图同时作为 first_frame 与 last_frame。
- 转场：不同图片分别作为 first_frame 与 last_frame。
- 参考模式：只传 reference_image，不得与首尾帧混用。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from media_edges import extract_last_frame
from production_gate import validate_pilot_approval, verify_frame_chain

from PIL import Image

from oil_motion_config import require_api_key


API_ROOT = "https://zenmux.ai/api/v1"
DEFAULT_MODEL = "minimax/minimax-h3-max"
TERMINAL_STATES = {"succeeded", "failed", "cancelled", "canceled"}
COMMON_RATIOS = {
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "1:1": 1.0,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
}


def local_image_data_uri(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"找不到图片：{path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def image_content(path: Path, role: str) -> dict[str, Any]:
    return {
        "type": "image_url",
        "role": role,
        "image_url": {
            "url": local_image_data_uri(path),
        },
    }


def infer_ratio(path: Path | None) -> str:
    if path is None:
        return "1:1"
    with Image.open(path) as image:
        actual = image.width / image.height
    return min(COMMON_RATIOS, key=lambda name: abs(COMMON_RATIOS[name] - actual))


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "oil-motion/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").replace(api_key, "[redacted]")
        raise RuntimeError(f"ZenMux API {exc.code}: {details}") from exc


def download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "oil-motion/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        output.write_bytes(response.read())


def find_job_id(response: dict[str, Any]) -> str:
    for key in ("id", "job_id", "jobId", "task_id", "taskId"):
        if response.get(key):
            return str(response[key])
    data = response.get("data")
    if isinstance(data, dict):
        return find_job_id(data)
    raise RuntimeError(f"提交成功但没有找到任务 ID：{response}")


def find_status(response: dict[str, Any]) -> str:
    for source in (response, response.get("data"), response.get("result")):
        if isinstance(source, dict):
            for key in ("status", "state"):
                if source.get(key):
                    return str(source[key]).lower()
    return "unknown"


def walk_for_url(value: Any, preferred_keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        for child in value.values():
            found = walk_for_url(child, preferred_keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = walk_for_url(child, preferred_keys)
            if found:
                return found
    return None


def redacted_metadata(
    payload: dict[str, Any],
    submit_response: dict[str, Any],
    final_response: dict[str, Any],
    production_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def redact_remote_urls(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    "<remote-url-redacted>"
                    if isinstance(child, str)
                    and child.startswith(("http://", "https://"))
                    else redact_remote_urls(child)
                )
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [redact_remote_urls(child) for child in value]
        return value

    safe_payload = dict(payload)
    safe_content = []
    for item in payload.get("content", []):
        if item.get("type") == "image_url":
            safe_content.append(
                {
                    "type": "image_url",
                    "role": item.get("role"),
                    "image_url": {
                        "url": "<local-image-data-uri>",
                    },
                }
            )
        else:
            safe_content.append(item)
    safe_payload["content"] = safe_content
    result = {
        "payload": safe_payload,
        "submit": redact_remote_urls(submit_response),
        "final": redact_remote_urls(final_response),
    }
    if production_gate is not None:
        result["productionGate"] = production_gate
    return result


def validate_production_gate(args: argparse.Namespace) -> dict[str, Any]:
    if args.segment_index < 1:
        raise ValueError("--segment-index 必须大于等于 1")
    stage = getattr(args, "stage", None) or "pilot"
    if stage == "pilot":
        return {"stage": "pilot", "segmentIndex": args.segment_index}

    if args.segment_index < 2:
        raise ValueError("production 阶段从第 2 段开始，--segment-index 必须大于等于 2")
    if not args.pilot_approval:
        raise ValueError("production 阶段必须提供 --pilot-approval")
    approval = validate_pilot_approval(
        args.pilot_approval,
        force=getattr(args, "force", False),
    )
    gate: dict[str, Any] = {
        "stage": "production",
        "segmentIndex": args.segment_index,
        "pilotApproval": str(
            Path(args.pilot_approval).expanduser().resolve()
        ),
        "continuityMode": args.continuity_mode,
    }
    if args.continuity_mode is None:
        raise ValueError(
            "production 阶段必须显式提供 --continuity-mode chain|independent"
        )
    approved_mode = approval["continuityMode"]
    if args.continuity_mode != approved_mode:
        raise ValueError(
            "production 连续模式与 Pilot 批准的 Concept Contract 不一致："
            f"合同要求 {approved_mode}，收到 {args.continuity_mode}"
        )
    if args.continuity_mode == "chain":
        if not args.previous_tail or not args.first_frame or not args.frame_chain_manifest:
            raise ValueError(
                "chain 模式必须同时提供 --previous-tail、--first-frame "
                "和 --frame-chain-manifest"
            )
        link = verify_frame_chain(
            args.previous_tail,
            args.first_frame,
            args.segment_index,
            args.frame_chain_manifest,
            force=getattr(args, "force", False),
        )
        gate["frameChain"] = link
        gate["frameChainManifest"] = str(
            Path(args.frame_chain_manifest).expanduser().resolve()
        )
    return gate


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError("必须提供 --prompt 或 --prompt-file")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    first = Path(args.first_frame).expanduser().resolve() if args.first_frame else None
    last = Path(args.last_frame).expanduser().resolve() if args.last_frame else None
    if args.loop_frame and args.last_frame:
        raise ValueError("--loop-frame 与 --last-frame 不能同时使用")
    if args.loop_frame:
        if not first:
            raise ValueError("--loop-frame 需要同时提供 --first-frame")
        last = first
    if last and not first:
        raise ValueError("--last-frame 需要同时提供 --first-frame")

    frame_mode = first is not None or last is not None
    reference_mode = bool(args.reference_image)
    if frame_mode and reference_mode:
        raise ValueError(
            "MiniMax H3 的 reference_image 与 first_frame/last_frame 互斥"
            "（接口错误 2013）。需要锁定身份时，请先把身份信息生成进首尾关键帧。"
        )
    if args.frames is not None and args.duration is not None:
        raise ValueError("--frames 与 --duration 不能同时传入")
    if args.frames is not None and args.frames < 2:
        raise ValueError("--frames 必须至少为 2")
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration 必须大于 0")

    if first:
        content.append(image_content(first, "first_frame"))
    if last:
        content.append(image_content(last, "last_frame"))
    reference_paths = [
        Path(raw_path).expanduser().resolve() for raw_path in args.reference_image
    ]
    for reference_path in reference_paths:
        content.append(image_content(reference_path, "reference_image"))

    payload: dict[str, Any] = {
        "model": args.model,
        "content": content,
        "resolution": args.resolution,
        "generate_audio": False,
        "watermark": False,
        "return_last_frame": True,
    }
    if args.frames is None:
        payload["duration"] = args.duration if args.duration is not None else 5
    payload["ratio"] = args.ratio or infer_ratio(
        first or (reference_paths[0] if reference_paths else None)
    )
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.frames is not None:
        payload["frames"] = args.frames
    return payload


def generate(args: argparse.Namespace) -> int:
    # 先做纯本地参数校验，避免因为缺少密钥而掩盖组合错误。
    payload = build_payload(args)
    gate_report = validate_production_gate(args)
    api_key = require_api_key()

    output = Path(args.output).expanduser().resolve()
    metadata = (
        Path(args.metadata).expanduser().resolve()
        if args.metadata
        else output.with_suffix(".job.json")
    )
    if output.exists() and not args.force:
        raise FileExistsError(f"输出已存在：{output}；确认后使用 --force")

    submit_response = request_json("POST", f"{API_ROOT}/videos", api_key, payload)
    job_id = find_job_id(submit_response)
    print(f"任务已提交：{job_id}", flush=True)

    deadline = time.monotonic() + args.timeout
    final_response = submit_response
    last_status = ""
    while time.monotonic() < deadline:
        final_response = request_json(
            "GET", f"{API_ROOT}/videos/{job_id}", api_key
        )
        status = find_status(final_response)
        if status != last_status:
            print(f"状态：{status}", flush=True)
            last_status = status
        if status in TERMINAL_STATES:
            break
        time.sleep(args.poll_interval)
    else:
        raise TimeoutError(f"等待视频超时：{args.timeout} 秒，任务 {job_id}")

    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        json.dumps(
            redacted_metadata(
                payload,
                submit_response,
                final_response,
                gate_report,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    status = find_status(final_response)
    if status != "succeeded":
        raise RuntimeError(f"视频生成未成功，状态：{status}；详情见 {metadata}")

    video_url = walk_for_url(
        final_response, ("video_url", "videoUrl", "url", "download_url")
    )
    if not video_url:
        raise RuntimeError(f"任务成功但没有找到视频地址；详情见 {metadata}")
    download(video_url, output)
    print(f"视频：{output}", flush=True)

    last_frame_output = (
        Path(args.last_frame_output).expanduser().resolve()
        if args.last_frame_output
        else output.with_name(f"{output.stem}-last-frame.jpg")
    )
    last_frame_url = walk_for_url(
        final_response, ("last_frame_url", "lastFrameUrl", "last_frame")
    )
    if last_frame_url:
        download(last_frame_url, last_frame_output)
        last_frame_source = "api"
    else:
        extract_last_frame(output, last_frame_output)
        last_frame_source = "video-fallback"
    print(f"尾帧：{last_frame_output}（来源：{last_frame_source}）", flush=True)

    metadata_payload = json.loads(metadata.read_text(encoding="utf-8"))
    metadata_payload["lastFrame"] = {
        "path": str(last_frame_output),
        "source": last_frame_source,
    }
    metadata.write_text(
        json.dumps(metadata_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"元数据：{metadata}", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="使用 ZenMux 的 MiniMax H3 生成并下载视频动作母版"
    )
    result.add_argument("--prompt")
    result.add_argument("--prompt-file")
    result.add_argument("--first-frame")
    result.add_argument("--last-frame")
    result.add_argument(
        "--loop-frame",
        action="store_true",
        help="把首帧同时作为尾帧，约束闭环",
    )
    result.add_argument(
        "--reference-image",
        action="append",
        default=[],
        help="参考模式，可重复传入；不得与首帧、尾帧或闭环模式混用",
    )
    result.add_argument("--model", default=DEFAULT_MODEL)
    result.add_argument(
        "--resolution",
        default="768p",
        help="MiniMax H3 使用 768p 或 2K；其他模型按其原生参数传入",
    )
    result.add_argument(
        "--ratio",
        help="输出画幅；有首帧时默认推断最接近的常用画幅，否则默认 1:1",
    )
    result.add_argument(
        "--duration",
        type=int,
        help="视频秒数；未传 --frames 时默认 5，不能与 --frames 同时使用",
    )
    result.add_argument("--seed", type=int)
    result.add_argument("--frames", type=int)
    result.add_argument(
        "--stage",
        choices=("pilot", "production"),
        default="pilot",
        help="阶段类型：默认 pilot（直接生成与验证）；production 阶段校验 Pilot 批准与连续性",
    )
    result.add_argument("--segment-index", type=int, default=1)
    result.add_argument("--pilot-approval")
    result.add_argument(
        "--continuity-mode",
        choices=("chain", "independent"),
        help="production 阶段必填；chain 会校验上一段尾帧与本段首帧 SHA-256",
    )
    result.add_argument("--previous-tail")
    result.add_argument("--frame-chain-manifest")
    result.add_argument("--output", required=True)
    result.add_argument("--last-frame-output")
    result.add_argument("--metadata")
    result.add_argument("--poll-interval", type=float, default=12.0)
    result.add_argument("--timeout", type=float, default=1200.0)
    result.add_argument("--force", action="store_true")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(generate(parser().parse_args()))
    except (FileNotFoundError, FileExistsError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1) from error
