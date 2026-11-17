# -*- coding: utf-8 -*-
"""本地服务生命周期：单实例、端口、打开浏览器、关页退出。

HTTP 路由与业务在 app/api/app.py；这里只管进程怎么起来、怎么退出。
"""
import ctypes
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from werkzeug.serving import make_server

import app.config as config
from app.api import alive, runtime
from app.api.app import create_app
from app.infra import media
from app.infra import store as sqlite_store
from app.infra.logging import log
from app.services import backup as backup_service

ROOT = config.ROOT
WEB = str(config.WEB_DIR)

NO_BROWSER = ('--no-browser' in sys.argv) or (os.environ.get('CAIGOU_NO_BROWSER') == '1')
OPEN_PATH = '/index.html'
for _arg in sys.argv[1:]:
    if _arg.startswith('--open='):
        OPEN_PATH = _arg.split('=', 1)[1] or OPEN_PATH
        if not OPEN_PATH.startswith('/'):
            OPEN_PATH = '/' + OPEN_PATH

PORT_FROM, PORT_TO = 8899, 8930
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
APP_VER = runtime.APP_VER
APP_ID = runtime.APP_ID
STOP = runtime.STOP


def _norm_root(path):
    """Windows 路径比较：忽略大小写与末尾分隔符"""
    return os.path.normcase(os.path.normpath(str(path or '')))


def _port_open(port):
    try:
        with socket.socket() as sock:
            sock.settimeout(0.08)
            return sock.connect_ex(('127.0.0.1', port)) == 0
    except OSError:
        return False


def scan_instances():
    """扫描端口范围，返回 [(端口, 系统目录, 版本, 指纹)]"""
    found = []
    for port in range(PORT_FROM, PORT_TO + 1):
        if not _port_open(port):
            continue
        try:
            with OPENER.open('http://127.0.0.1:%d/__ping' % port, timeout=1.5) as resp:
                if resp.status != 200:
                    continue
                parts = resp.read().decode('utf-8', 'replace').split('|')
        except Exception:
            continue
        if parts[0].strip() != 'pong':
            continue
        found.append((port,
                      parts[1].strip() if len(parts) > 1 else '',
                      parts[2].strip() if len(parts) > 2 else '',
                      parts[3].strip() if len(parts) > 3 else ''))
    return found


def already_running():
    """同目录、同版本的实例端口；没有则 None"""
    me = _norm_root(ROOT)
    for port, root, version, ident in scan_instances():
        if _norm_root(root) == me and version == APP_VER and ident == APP_ID:
            return port
    return None


def find_port():
    for port in range(PORT_FROM, PORT_TO + 1):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return None


def open_in_browser(port, path=None):
    """URL 带时间戳，避免浏览器复用旧标签页"""
    if NO_BROWSER:
        log('本次设定：不自动打开浏览器')
        return ''
    target = path or OPEN_PATH
    stamp = int(time.time() * 1000)
    if '#' in target:
        base, fragment = target.split('#', 1)
        url = 'http://127.0.0.1:%d%s?t=%d#%s' % (port, base, stamp, fragment)
    else:
        url = 'http://127.0.0.1:%d%s?t=%d' % (port, target, stamp)
    try:
        webbrowser.open(url)
    except Exception as exc:
        log('打开浏览器失败: %r' % (exc,))
    return url


def _arm_auto_stop(port):
    """让已经在跑的实例也支持“关掉网页就退出”"""
    try:
        OPENER.open('http://127.0.0.1:%d/__arm' % port, timeout=2).read()
        log('已通知实例 %d：启用关闭网页自动退出' % port)
    except Exception as exc:
        log('通知自动退出失败: %r' % (exc,))


def _watch_pages():
    """所有页面都关掉后自动退出；刷新会在宽限期内重连"""
    log('页面在线监测已启动（关掉网页 %.0f 秒后自动退出）' % alive.GRACE_SECONDS)
    was_empty = False
    while not STOP.is_set():
        if STOP.wait(0.5):
            break
        snap = alive.snapshot()
        if snap['armed'] and snap['seen'] and not snap['clients']:
            if not was_empty:
                log('页面已全部关闭，%.0f 秒后自动退出' % alive.GRACE_SECONDS)
                was_empty = True
        elif was_empty:
            log('页面已重新连上（刷新/新标签），取消自动退出')
            was_empty = False
        if alive.should_stop():
            log('页面关闭超过 %.0f 秒，自动退出' % alive.GRACE_SECONDS)
            STOP.set()
            break


def _landing(first_run):
    """首次没有数据时进向导；新前端用 hash 路由，旧页面用 welcome.html"""
    spa = os.path.isdir(os.path.join(WEB, 'assets'))
    if spa:
        return '/#/welcome' if first_run else '/'
    return '/welcome.html' if first_run else OPEN_PATH


def main():
    log('---- 启动 ----')
    try:
        sqlite_store.ensure_database()
        log('SQLite 已就绪: %s' % sqlite_store.DB_PATH)
    except Exception as exc:
        log('SQLite 初始化失败: %r' % (exc,))
        _msgbox('数据库初始化失败：%s' % exc)
        return

    try:
        copied = media.ensure_migrated()
        if copied:
            log('图片已迁移到 data/media：%d 张' % copied)
    except Exception as exc:
        log('图片迁移失败（不影响使用）: %r' % (exc,))

    try:
        backup_service.daily_if_needed()
    except Exception as exc:
        log('每日备份失败（不影响使用）: %r' % (exc,))

    if not os.path.exists(os.path.join(WEB, 'index.html')):
        _msgbox('找不到网页文件 web\\index.html，文件夹不完整，请重新解压。')
        return

    first_run = sqlite_store.product_count() == 0
    if first_run:
        log('数据库中还没有产品，打开首启向导')

    running = already_running()
    if running:
        log('已有实例在 %d，直接打开浏览器' % running)
        if not NO_BROWSER:
            _arm_auto_stop(running)
        open_in_browser(running, _landing(first_run))
        return

    port = find_port()
    if port is None:
        _msgbox('端口 8899-8930 都被占用，请重启电脑后再试。')
        return

    alive.set_armed(not NO_BROWSER)
    application = create_app()
    httpd = make_server('127.0.0.1', port, application, threaded=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=_watch_pages, daemon=True).start()

    landing = _landing(first_run)
    log('服务已启动: http://127.0.0.1:%d%s' % (port, landing))
    open_in_browser(port, landing)

    while not STOP.is_set():
        time.sleep(0.5)

    log('服务已结束')
    try:
        httpd.shutdown()
    except Exception:
        pass


def _msgbox(text, icon=0x10):
    """无窗口模式下用系统弹窗提示"""
    try:
        ctypes.windll.user32.MessageBoxW(0, text, '采购下单系统', icon)
    except Exception:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('异常: %r' % (exc,))
        _msgbox('启动失败：%s\n请双击 maintenance.bat，选“查看日志”，把日志发给维护人。' % exc)
