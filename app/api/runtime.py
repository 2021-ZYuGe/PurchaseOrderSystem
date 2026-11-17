# -*- coding: utf-8 -*-
"""进程级共享状态：停止信号与程序指纹。"""
import hashlib
import os
import threading

import app.config as config

STOP = threading.Event()


def build_stamp():
    digest = hashlib.md5()
    for rel in config.STAMP_FILES:
        path = os.path.join(config.ROOT, rel.replace('/', os.sep))
        try:
            stat = os.stat(path)
            digest.update(('%s|%d|%d' % (rel, stat.st_size, int(stat.st_mtime))).encode('utf-8'))
        except OSError:
            digest.update(rel.encode('utf-8'))
    return digest.hexdigest()[:8].upper()


APP_ID = build_stamp()
APP_VER = config.VERSION
