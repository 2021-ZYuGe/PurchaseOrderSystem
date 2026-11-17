# -*- coding: utf-8 -*-
"""批次导入：易快报与本地文件夹。"""
from flask import request

from app.api.responses import ApiError, ok
from app.services import imports as import_service


def _unwrap(result, default='导入失败'):
    if isinstance(result, dict) and result.get('ok'):
        return result.get('data') if result.get('data') is not None else result
    message = ''
    if isinstance(result, dict):
        message = str(result.get('error') or result.get('message') or '')
    message = message or default
    if '已有导入任务' in message or '正在导入' in message or '在跑' in message:
        raise ApiError('import_running', message, 409)
    raise ApiError('import_failed', message)


def preview():
    body = request.get_json(silent=True) or {}
    return ok(_unwrap(import_service.preview_ekb(body), '预览失败'))


def start_ekb():
    body = request.get_json(silent=True) or {}
    return ok(_unwrap(import_service.start_ekb(body), '启动导入失败'))


def start_folder():
    body = request.get_json(silent=True) or {}
    if not str(body.get('path') or '').strip():
        raise ApiError('invalid_argument', '请先选择合同文件夹')
    return ok(_unwrap(import_service.start_folder(body), '启动导入失败'))


def current():
    return ok(import_service.status())


def history():
    try:
        limit = max(1, min(50, int(request.args.get('limit') or 10)))
    except ValueError:
        limit = 10
    return ok({'items': import_service.history(limit)})
