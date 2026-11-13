# -*- coding: utf-8 -*-
"""
开机自动把采购下单系统的服务跑起来（不弹网页）

放在 Windows「启动」文件夹里，每次开机/登录后自动执行一次：
  - 服务已经在跑 → 什么都不做
  - 服务没跑     → 后台拉起来（用 --no-browser，不会开机就弹浏览器烦你）
全程静默，任何异常都不弹窗。
"""
import os
import socket
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
PORT_FROM, PORT_TO = 8899, 8930
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _norm_root(p):
    return os.path.normcase(os.path.normpath(str(p or '')))


def running():
    """本目录的系统是否已经在跑；跑着就返回端口

    必须核对系统目录：旧文件夹没删时，端口上跑的可能是旧系统，
    那时不能当作"已经在跑"，要让启动器接管（它会停掉旧实例）。
    """
    me = _norm_root(ROOT)
    for p in range(PORT_FROM, PORT_TO + 1):
        try:
            with socket.socket() as s:
                s.settimeout(0.08)
                if s.connect_ex(('127.0.0.1', p)) != 0:
                    continue
        except Exception:
            continue
        try:
            # 只认正式服务的 /__ping，避免把静态预览页当成系统
            r = OPENER.open('http://127.0.0.1:%d/__ping' % p, timeout=1.5)
            if r.status != 200:
                continue
            parts = r.read().decode('utf-8', 'replace').split('|')
            if parts[0].strip() != 'pong':
                continue
            if len(parts) > 1 and _norm_root(parts[1].strip()) == me:
                return p
        except Exception:
            continue
    return None


def main():
    try:
        if not os.path.isdir(ROOT):
            return
        if running():
            return
        exe = os.path.join(ROOT, '运行环境', 'pythonw.exe')
        if not os.path.exists(exe):
            return
        subprocess.Popen([exe, os.path.join(HERE, '打开系统_静默.py'), '--no-browser'],
                         cwd=ROOT)
        # 最多等 30 秒，确认真的起来了
        for _ in range(60):
            time.sleep(0.5)
            if running():
                return
    except Exception:
        pass


if __name__ == '__main__':
    main()
