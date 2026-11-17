# -*- coding: utf-8 -*-
"""页面在线状态：最后一个页面关闭后，服务自动退出。

页面用 SSE 连 /__alive；关闭时 sendBeacon 到 /__bye。
刷新会在宽限期内重新连上，不会误退。
"""
import threading
import time

GRACE_SECONDS = 10.0
MAX_CLIENTS = 12

_lock = threading.Lock()
_clients = {}
_seen = False
_armed = True
_empty_since = None


def register(client_id):
    """登记一个页面；超出上限返回 False（不参与计数）"""
    global _seen, _empty_since
    with _lock:
        if client_id not in _clients and len(_clients) >= MAX_CLIENTS:
            return False
        _clients[client_id] = time.time()
        _seen = True
        _empty_since = None
    return True


def touch(client_id):
    with _lock:
        if client_id in _clients:
            _clients[client_id] = time.time()


def unregister(client_id):
    global _empty_since
    with _lock:
        _clients.pop(client_id, None)
        if not _clients:
            _empty_since = time.time()


def arm():
    """常驻实例收到“按关页退出处理”的指令"""
    global _armed, _empty_since
    with _lock:
        _armed = True
        _empty_since = None


def set_armed(value):
    """--no-browser 启动的实例不自动退出"""
    global _armed
    with _lock:
        _armed = bool(value)


def count():
    with _lock:
        return len(_clients)


def should_stop(now=None):
    with _lock:
        if not _armed or not _seen or _clients or _empty_since is None:
            return False
        return (now or time.time()) - _empty_since >= GRACE_SECONDS


def snapshot():
    with _lock:
        return {'clients': len(_clients), 'seen': _seen,
                'armed': _armed, 'empty_since': _empty_since}
