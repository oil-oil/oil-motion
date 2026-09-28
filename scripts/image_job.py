#!/usr/bin/env python3
"""通过 ZenMux 图片模型生成关键帧 PNG。

- `--background` 必填：`page` 路线传 transparent，`video` 路线传 opaque，不静默猜测。
- 传 `--image` 时走改图接口，用参考图锁定产品结构、角色身份或上一张关键帧。
- transparent 结果会检查真实 Alpha；四角不透明或没有可见主体时拒收，不交给后续色键合成。
"""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from oil_motion_config import require_api_key

API_ROOT = "https://zenmux.ai/api/v1"
DEFAULT_IMAGE_MODEL = "openai/gpt-image-2.5-flare"
DEFAULT_SIZE = "1024x1024"
BACKGROUNDS = ("transparent", "opaque")
QUALITIES = ("auto", "low", "medium", "high")
MAX_REFERENCES = 16
MAX_REFERENCE_BYTES = 50 * 1024 * 1024
ALPHA_TRANSPARENT = 16
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}")


def redact(text: str, api_key: str = "") -> str:
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return KEY_PATTERN.sub("[redacted]", text)


def parse_size(size: str, model: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2,4})x(\d{2,4})", size)
    if not match:
        raise ValueError(f"--size 写成 宽x高（如 2048x1152），当前是 {size}")
    width, height = int(match.group(1)), int(match.group(2))
    if model.startswith("openai/gpt-image-2"):
        problems = []
        if width % 16 or height % 16:
            problems.append("宽和高都要是 16 的倍数")
        if max(width, height) > 3840:
            problems.append("最长边不超过 3840")
        if max(width, height) / min(width, height) > 3:
            problems.append("长短边之比不超过 3:1")
        if not 655_360 <= width * height <= 8_294_400:
            problems.append("总像素在 655,360 到 8,294,400 之间")
        if problems:
            raise ValueError(f"--size {size} 不可用：{'；'.join(problems)}")
    return width, height


def check_references(paths: list[str]) -> list[Path]:
    if len(paths) > MAX_REFERENCES:
        raise ValueError(f"参考图最多 {MAX_REFERENCES} 张，当前 {len(paths)} 张")
    result = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"找不到参考图：{path}")
        if path.stat().st_size > MAX_REFERENCE_BYTES:
            raise ValueError(f"参考图超过 50MB：{path}")
        result.append(path)
    return result


def multipart(fields: dict[str, str], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----oil-motion-{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
    for name, path in files:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def build_request(
    prompt: str,
    background: str,
    size: str,
    model: str,
    quality: str,
    references: list[Path],
) -> tuple[str, dict[str, str]]:
    """返回接口路径与请求字段；不含密钥。"""
    fields = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": "png",
        "n": "1",
    }
    return ("/images/edits" if references else "/images/generations"), fields


def send(path: str, fields: dict[str, str], references: list[Path], api_key: str, timeout: float) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "oil-motion/1.0",
    }
    if references:
        data, headers["Content-Type"] = multipart(fields, [("image[]", item) for item in references])
    else:
        payload = {**fields, "n": 1}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{API_ROOT}{path}", data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = redact(exc.read().decode("utf-8", errors="replace")[:2000], api_key)
        raise RuntimeError(f"ZenMux Image API {exc.code}: {details}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"图片接口返回了无效 JSON：{redact(body[:500], api_key)}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("图片接口返回的顶层数据不是对象")
    return result


def image_bytes(result: dict[str, Any], timeout: float) -> bytes:
    items = result.get("data")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise RuntimeError("图片接口没有返回图片")
    item = items[0]
    if isinstance(item.get("b64_json"), str):
        try:
            return base64.b64decode(item["b64_json"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("返回的图片数据不是有效的 Base64") from exc
    if isinstance(item.get("url"), str):
        request = urllib.request.Request(item["url"], headers={"User-Agent": "oil-motion/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    raise RuntimeError("返回的图片项既没有 b64_json 也没有 url")


def alpha_problem(image: Image.Image) -> str | None:
    """page 路线关键帧的透明验收：真实 Alpha、四角透明、存在可见主体。"""
    if "A" not in image.getbands():
        return "没有 Alpha 通道"
    alpha = image.getchannel("A")
    width, height = image.size
    corners = [alpha.getpixel(point) for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
    if max(corners) > ALPHA_TRANSPARENT:
        return f"四角不透明（Alpha {corners}），背景没有真正透明"
    if alpha.getextrema()[1] <= ALPHA_TRANSPARENT:
        return "整张图透明，没有可见主体"
    return None


def generate_image(
    prompt: str,
    output_path: Path,
    background: str,
    size: str = DEFAULT_SIZE,
    model: str = DEFAULT_IMAGE_MODEL,
    quality: str = "auto",
    references: list[Path] | None = None,
    force: bool = False,
    timeout: float = 600,
) -> Path:
    references = references or []
    if output_path.suffix.lower() != ".png":
        raise ValueError(f"关键帧输出使用 .png：{output_path.name}")
    rejected = output_path.with_name(f"{output_path.stem}.rejected.png")
    for target in (output_path, rejected):
        if target.exists() and not force:
            raise FileExistsError(f"输出文件已存在：{target}；确认后使用 --force")

    api_key = require_api_key()
    path, fields = build_request(prompt, background, size, model, quality, references)
    mode = f"改图（{len(references)} 张参考图）" if references else "文生图"
    print(f"正在提交关键帧：{model} {size} {background}，{mode}…", flush=True)
    data = image_bytes(send(path, fields, references, api_key, timeout), timeout)

    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            image = opened.copy()
    except OSError as exc:
        raise RuntimeError("返回的数据不是可读取的图片") from exc

    problem = alpha_problem(image) if background == "transparent" else None
    target = rejected if problem else output_path
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")
    width, height = image.size
    print(f"实际尺寸：{width}x{height}（宽高比 {width / height:.3f}）", flush=True)
    if problem:
        raise RuntimeError(f"透明验收失败：{problem}。结果已另存为 {target}，不要用作 page 路线关键帧")
    print(f"关键帧已保存：{target}", flush=True)
    return target


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    prompt_group = result.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="提示词文本")
    prompt_group.add_argument("--prompt-file", help="提示词文件")
    result.add_argument("--output", required=True, help="输出 PNG 路径")
    result.add_argument(
        "--background",
        required=True,
        choices=BACKGROUNDS,
        help="background_owner=page 传 transparent；background_owner=video 传 opaque",
    )
    result.add_argument(
        "--image",
        action="append",
        default=[],
        help="参考图，可重复；顺序即提示词中的“图 1、图 2”",
    )
    result.add_argument("--size", default=DEFAULT_SIZE, help="宽x高，按合同 aspect_ratio 选择")
    result.add_argument("--model", default=DEFAULT_IMAGE_MODEL, help="图片模型 ID")
    result.add_argument("--quality", default="auto", choices=QUALITIES)
    result.add_argument("--timeout", type=float, default=600, help="请求超时秒数")
    result.add_argument("--force", action="store_true", help="覆盖已存在的输出文件")
    result.add_argument("--dry-run", action="store_true", help="只校验参数并显示请求摘要，不调用接口、不需要密钥")
    return result


def main() -> int:
    args = parser().parse_args()
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("提示词是空的")
    parse_size(args.size, args.model)
    references = check_references(args.image)
    output = Path(args.output).expanduser().resolve()
    if args.dry_run:
        path, fields = build_request(prompt, args.background, args.size, args.model, args.quality, references)
        print(json.dumps(
            {"endpoint": f"{API_ROOT}{path}", **fields, "references": [str(item) for item in references], "output": str(output)},
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    generate_image(
        prompt=prompt,
        output_path=output,
        background=args.background,
        size=args.size,
        model=args.model,
        quality=args.quality,
        references=references,
        force=args.force,
        timeout=args.timeout,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1) from None
