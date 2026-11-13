# -*- coding: utf-8 -*-
"""兼容层：真实实现已搬到 app/domain/contract_doc.py。

服务端按文件路径加载生成器（改完自动重载），P1 起指向新位置；
这个文件只负责让旧引用继续可用。
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain.contract_doc import *          # noqa: F401,F403
from app.domain.contract_doc import _utf8_console

if __name__ == '__main__':
    runpy.run_module('app.domain.contract_doc', run_name='__main__')
