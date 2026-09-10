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
import secure_credentials


CONFIG_FILE_ENV = "OIL_MOTION_CONFIG_FILE"
API_KEY_ENV = "ZENMUX_API_KEY"
CREDENTIAL_REF = 'oil-motion/zenmux/default'


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


def configured_api_key(path: Path | None = None) -> tuple[str, str]:
    environment_key = os.environ.get(API_KEY_ENV, "").strip()
    if environment_key:
        return environment_key, API_KEY_ENV
    config = read_config(path)
    zenmux = config.get("zenmux")
    if isinstance(zenmux, dict):
        if zenmux.get('credential_ref'):
            key = secure_credentials.read(zenmux['credential_ref'])
            return (key, '系统凭据库') if key else ('', '')
        stored_key = zenmux.get("api_key")
        if isinstance(stored_key, str) and stored_key.strip():
            return stored_key.strip(), str(path or config_path())
    return "", ""


def require_api_key(path: Path | None = None) -> str:
    api_key, _ = configured_api_key(path)
    if api_key:
        return api_key
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


def set_api_key(path: Path | None = None) -> int:
    key = getpass.getpass("ZenMux API Key：").strip()
    if not key:
        raise RuntimeError("API Key 不能为空")
    config = read_config(path)
    zenmux = config.get("zenmux")
    if not isinstance(zenmux, dict):
        zenmux = {}
    secure_credentials.save(CREDENTIAL_REF, key)
    zenmux.pop('api_key', None)
    zenmux['credential_ref'] = CREDENTIAL_REF
    config["zenmux"] = zenmux
    target = write_config(config, path)
    print(f"已保存：{target}")
    return 0


def clear_api_key(path: Path | None = None) -> int:
    target = path or config_path()
    config = read_config(target)
    zenmux = config.get("zenmux")
    if isinstance(zenmux, dict):
        reference = zenmux.get('credential_ref')
        if reference:
            secure_credentials.delete(reference)
            zenmux.pop('credential_ref', None)
        zenmux.pop("api_key", None)
        if zenmux:
            config["zenmux"] = zenmux
        else:
            config.pop("zenmux", None)
    if config:
        write_config(config, target)
    elif target.exists():
        target.unlink()
    print("已清除 ZenMux API Key")
    return 0


def show_status(path: Path | None = None) -> int:
    _, source = configured_api_key(path)
    if source:
        print(f"ZenMux API Key 已配置（来源：{source}）")
        return 0
    print("ZenMux API Key 尚未配置")
    return 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="管理 Oil Motion 的本地配置")
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("set", help="在隐藏输入框中保存 ZenMux API Key")
    subparsers.add_parser("status", help="检查 API Key 是否已经配置")
    subparsers.add_parser("clear", help="清除已经保存的 API Key")
    subparsers.add_parser("path", help="显示配置文件路径")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "set":
        return set_api_key()
    if args.command == "status":
        return show_status()
    if args.command == "clear":
        return clear_api_key()
    print(config_path())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1) from error
