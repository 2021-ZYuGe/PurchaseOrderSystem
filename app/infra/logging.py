# -*- coding: utf-8 -*-
"""日志：标准 logging，按天滚动写到 data/logs/app.log。"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import app.config as config

_LOGGER = None


def _build_logger():
    logger = logging.getLogger('purchase_order')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = Path(config.LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(
            str(path), when='midnight', backupCount=14, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s  %(message)s', '%H:%M:%S'))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


def log(msg):
    global _LOGGER
    try:
        if _LOGGER is None:
            _LOGGER = _build_logger()
        _LOGGER.info(str(msg))
    except Exception:
        pass
