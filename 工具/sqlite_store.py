# -*- coding: utf-8 -*-
"""兼容层：真实实现已搬到 app/infra/store.py。

保留这个文件，是为了让 工具/ 下的脚本（合并新合同、回填合同期限、自检清理…）
继续 `import sqlite_store` 就能用，P1 阶段不动它们的入口。
新代码请直接 `from app.infra import store`。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infra.store import *          # noqa: F401,F403
from app.infra import store as _impl

# import * 不会带下划线名字；这个函数外部在用，显式补上
_candidate_contract_dirs = _impl._candidate_contract_dirs
