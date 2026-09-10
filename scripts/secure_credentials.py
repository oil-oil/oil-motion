"""可信程序内部使用的系统凭据适配器，不提供明文输出 CLI。"""
from __future__ import annotations
import importlib
import sys

SERVICE = 'org.oiloil.skill-credentials'

def backend():
    """显式选择系统后端，拒绝自动退回明文或临时存储。"""
    target = {
        'darwin': ('keyring.backends.macOS', 'Keyring'),
        'win32': ('keyring.backends.Windows', 'WinVaultKeyring'),
        'linux': ('keyring.backends.SecretService', 'Keyring'),
    }.get(sys.platform)
    if target is None:
        raise RuntimeError('当前系统未实现安全凭据后端；请使用运行时环境变量')
    try:
        result = getattr(importlib.import_module(target[0]), target[1])()
        if result.priority <= 0:
            raise RuntimeError('后端不可用')
        return result
    except Exception:
        raise RuntimeError('系统凭据库不可用；请检查 keyring 依赖与系统解锁状态，或使用运行时环境变量') from None

def read(reference: str) -> str:
    try:
        return backend().get_password(SERVICE, reference) or ''
    except Exception:
        raise RuntimeError('无法读取系统凭据；不会降级保存明文') from None

def save(reference: str, secret: str) -> None:
    if not secret or '\n' in secret or '\r' in secret:
        raise ValueError('凭据必须是非空单行文本')
    try:
        backend().set_password(SERVICE, reference, secret)
    except Exception:
        raise RuntimeError('系统凭据保存失败；原配置未被改为明文') from None

def delete(reference: str) -> None:
    try:
        store = backend()
        if store.get_password(SERVICE, reference) is not None:
            store.delete_password(SERVICE, reference)
    except Exception:
        raise RuntimeError('系统凭据删除失败；请检查后端状态') from None
