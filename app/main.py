# -*- coding: utf-8 -*-
"""采购下单系统 · 进程入口。

用法：
    python -m app.main
    pythonw app/main.py
    （或双击 工具/打开系统_静默.py / 启动网页版.bat，最终都走到这里）

只负责启动与兜底异常提示，具体服务在 app/api/server.py。
"""
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run():
    try:
        from app.api import server
        server.main()
    except Exception as e:
        from app.infra.logging import log
        log('异常: %r' % (e,))
        try:
            from app.api.server import _msgbox
            _msgbox('启动失败：%s\n请双击「工具\\诊断问题.bat」并把诊断报告发给小简。' % e)
        except Exception:
            pass


# 兼容旧调用名
main = run


if __name__ == '__main__':
    run()
