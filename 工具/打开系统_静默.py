# -*- coding: utf-8 -*-
"""兼容层：真实入口已搬到 app/main.py。

bat、快捷方式、开机自启脚本都还指着这个文件，所以保留它。
新代码请直接用 `python -m app.main`。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import run

if __name__ == '__main__':
    run()
