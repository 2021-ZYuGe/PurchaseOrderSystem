# -*- coding: utf-8 -*-
"""采购下单系统 · 进程入口。

用法：
    python -m app
    pythonw -m app
    （日常双击根目录的「采购下单系统」快捷方式，最终都走到这里）

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
            _msgbox('启动失败：%s\n请双击 maintenance.bat，选“查看日志”，把日志发给维护人。' % e)
        except Exception:
            pass


# 兼容旧调用名
main = run


if __name__ == '__main__':
    run()
