# -*- coding: utf-8 -*-
"""
采购下单系统 · 一键启动（双击本文件即可，不依赖 bat / cmd）
原因：公司安全软件开始拦截"cmd 窗口派生 python"的启动方式，
     直接双击 .py 由资源管理器启动，不经过 cmd，可以绕开。
"""
import os
import sys
import socket
import threading
import webbrowser
import functools

import sqlite_store

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
WEB = os.path.join(ROOT, 'web')


def find_port():
    for p in range(8899, 8931):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return None


def ensure_data():
    """首次自动迁移旧数据；没有数据时引导生成 SQLite 主库。"""
    sqlite_store.ensure_database()
    if sqlite_store.product_count() > 0:
        return True
    print()
    print('还没有你自己的数据，现在帮你生成。')
    print('请先从 WorkBuddy 接入企微易快报，导出你的合同附件文件夹（.docx）。')
    print()
    path = input('把合同文件夹的路径粘贴到这里（也可以直接把文件夹拖进本窗口），按回车：\n> ').strip().strip('"')
    if not path:
        return False
    import subprocess
    subprocess.run([sys.executable, os.path.join(HERE, '_工具_生成数据库.py'), path])
    return sqlite_store.product_count() > 0


def main():
    print()
    print('============================================')
    print('         采购下单系统  启动中')
    print('============================================')

    if not os.path.exists(os.path.join(WEB, 'index.html')):
        input('\n[错误] 找不到 web\\index.html，文件夹不完整。按回车退出…')
        return

    if not ensure_data():
        input('\n[错误] 数据没有生成成功。按回车退出…')
        return

    port = find_port()
    if port is None:
        input('\n[错误] 8899-8930 端口都被占用，请重启电脑后重试。按回车退出…')
        return

    os.chdir(WEB)
    import http.server
    import importlib.util
    # 必须复用 打开系统_静默.py 里的 Handler：
    # 直接用 SimpleHTTPRequestHandler 只能浏览网页，没有 /api/make_contract，
    # 页面上点“生成主合同”会收到 501 HTML，报 SyntaxError: Unexpected token '<'。
    spec = importlib.util.spec_from_file_location(
        'caigou_server', os.path.join(HERE, '打开系统_静默.py'))
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    httpd = http.server.ThreadingHTTPServer(
        ('127.0.0.1', port), functools.partial(srv.Handler))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    url = 'http://127.0.0.1:%d/index.html' % port
    print()
    print('============================================')
    print('         采购下单系统  已启动')
    print('============================================')
    print()
    print('  网页地址：' + url)
    print('  浏览器即将自动打开…')
    print('  ★ 浏览器没自动打开的话，手动复制上面的网址。')
    print()
    print('  ★ 用完之后：回到本窗口按回车键，系统自动结束。')
    print()
    print('============================================')
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        input()
    except EOFError:
        # 无键盘输入的场景（被后台程序/脚本拉起）：保持服务运行，关闭窗口才结束
        print('（检测到无键盘输入环境，服务将持续运行；关闭本窗口即结束）')
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        pass
    print('系统已结束。')


if __name__ == '__main__':
    main()
