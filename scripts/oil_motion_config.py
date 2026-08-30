#!/usr/bin/env python3
"""保存并读取 Oil Motion 的本地配置。"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


CONFIG_FILE_ENV = "OIL_MOTION_CONFIG_FILE"

# Supported video providers. zenmux stays the default; orcarouter mirrors it as
# a first-class provider so users can route the same MiniMax video model through
# the OrcaRouter gateway without treating it as an anonymous base URL.
PROVIDERS = ("zenmux", "orcarouter")
API_KEY_ENV = "ZENMUX_API_KEY"
ORCAROUTER_API_KEY_ENV = "ORCAROUTER_API_KEY"
ORCAROUTER_SECTION = "orcarouter"


def provider_config_section(provider: str) -> str:
    if provider == "orcarouter":
        return ORCAROUTER_SECTION
    return "zenmux"


def provider_api_key_env(provider: str) -> str:
    if provider == "orcarouter":
        return ORCAROUTER_API_KEY_ENV
    return API_KEY_ENV


def config_path() -> Path:
    override = os.environ.get(CONFIG_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return root / "oil-motion" / "config.json"


def read_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"配置文件不是有效的 JSON：{target}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"配置文件的根节点必须是对象：{target}")
    return value


def configured_api_key(
    path: Path | None = None, provider: str = "zenmux"
) -> tuple[str, str]:
    env_name = provider_api_key_env(provider)
    environment_key = os.environ.get(env_name, "").strip()
    if environment_key:
        return environment_key, env_name
    config = read_config(path)
    section = provider_config_section(provider)
    stored = config.get(section)
    if isinstance(stored, dict):
        stored_key = stored.get("api_key")
        if isinstance(stored_key, str) and stored_key.strip():
            return stored_key.strip(), str(path or config_path())
    return "", ""


def require_api_key(path: Path | None = None, provider: str = "zenmux") -> str:
    api_key, _ = configured_api_key(path, provider)
    if api_key:
        return api_key
    if provider == "orcarouter":
        raise RuntimeError(
            "尚未配置 OrcaRouter API Key。请先运行 "
            "`python3 scripts/oil_motion_config.py set --provider orcarouter`，"
            "配置一次后会自动复用。"
        )
    raise RuntimeError(
        "尚未配置 ZenMux API Key。请先运行 "
        "`python3 scripts/oil_motion_config.py set`，配置一次后会自动复用。"
    )


def write_config(config: dict[str, Any], path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    temporary.replace(target)
    return target


def set_api_key(path: Path | None = None, provider: str = "zenmux") -> int:
    label = "OrcaRouter" if provider == "orcarouter" else "ZenMux"
    key = getpass.getpass(f"{label} API Key：").strip()
    if not key:
        raise RuntimeError("API Key 不能为空")
    config = read_config(path)
    section = provider_config_section(provider)
    stored = config.get(section)
    if not isinstance(stored, dict):
        stored = {}
    stored["api_key"] = key
    config[section] = stored
    target = write_config(config, path)
    print(f"已保存：{target}")
    return 0


def clear_api_key(path: Path | None = None, provider: str = "zenmux") -> int:
    label = "OrcaRouter" if provider == "orcarouter" else "ZenMux"
    target = path or config_path()
    config = read_config(target)
    section = provider_config_section(provider)
    stored = config.get(section)
    if isinstance(stored, dict):
        stored.pop("api_key", None)
        if stored:
            config[section] = stored
        else:
            config.pop(section, None)
    if config:
        write_config(config, target)
    elif target.exists():
        target.unlink()
    print(f"已清除 {label} API Key")
    return 0


def show_status(path: Path | None = None, provider: str = "zenmux") -> int:
    label = "OrcaRouter" if provider == "orcarouter" else "ZenMux"
    _, source = configured_api_key(path, provider)
    if source:
        print(f"{label} API Key 已配置（来源：{source}）")
        return 0
    print(f"{label} API Key 尚未配置")
    return 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="管理 Oil Motion 的本地配置")
    result.add_argument(
        "--provider",
        choices=PROVIDERS,
        default="zenmux",
        help="视频提供商：zenmux（默认）或 orcarouter",
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("set", help="在隐藏输入框中保存 API Key")
    subparsers.add_parser("status", help="检查 API Key 是否已经配置")
    subparsers.add_parser("clear", help="清除已经保存的 API Key")
    subparsers.add_parser("path", help="显示配置文件路径")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "set":
        return set_api_key(provider=args.provider)
    if args.command == "status":
        return show_status(provider=args.provider)
    if args.command == "clear":
        return clear_api_key(provider=args.provider)
    print(config_path())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1) from error
