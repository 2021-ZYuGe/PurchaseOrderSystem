# -*- coding: utf-8 -*-
"""日志：写 data/_运行日志.txt，格式与重构前完全一致。"""
import time

from app.config import LOG_PATH


def log(msg):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass
