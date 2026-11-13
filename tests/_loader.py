# -*- coding: utf-8 -*-
"""测试用模块加载器 —— 重构前后共用同一份测试。

P1 之后真实代码在 app/ 包里；P1 之前在 工具/ 下。
这里按"新位置优先、旧位置兜底"的顺序取模块，避免测试跟着重构改一遍。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_root_on_path():
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _tools_on_path():
    tools = str(ROOT / '工具')
    if tools not in sys.path:
        sys.path.insert(0, tools)


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def contract_doc():
    """合同生成器（domain 层）"""
    _ensure_root_on_path()
    if (ROOT / 'app' / 'domain' / 'contract_doc.py').exists():
        from app.domain import contract_doc as m
        return m
    return _load_by_path('_legacy_contract_doc', ROOT / '工具' / '生成主合同.py')


def store():
    """SQLite 数据层（infra 层）"""
    _ensure_root_on_path()
    if (ROOT / 'app' / 'infra' / 'store.py').exists():
        from app.infra import store as m
        return m
    _tools_on_path()
    import sqlite_store as m
    return m


def server():
    """HTTP 服务（api 层）"""
    _ensure_root_on_path()
    if (ROOT / 'app' / 'api' / 'server.py').exists():
        from app.api import server as m
        return m
    _tools_on_path()
    return _load_by_path('_legacy_server', ROOT / '工具' / '打开系统_静默.py')


def web_dir():
    return ROOT / 'web'


def data_dir():
    return ROOT / 'data'
