# -*- coding: utf-8 -*-
"""首启向导：选择目录、导入、恢复数据包。"""
from flask import request

from app.api.responses import ApiError, ok
from app.services import setup as setup_service


def status():
    return ok(setup_service.status())


def pick_folder():
    return ok({'path': setup_service.pick_folder()})


def import_contracts():
    body = request.get_json(silent=True) or {}
    result = setup_service.import_contracts(body.get('path'))
    if not result.get('ok'):
        raise ApiError('invalid_argument', str(result.get('error') or '导入失败'))
    return ok({'started': True})


def restore():
    """请求体是 sqlite 或 zip 的原始字节"""
    raw = request.get_data(cache=False)
    if not raw:
        raise ApiError('invalid_argument', '没有收到文件')
    result = setup_service.restore_any(raw)
    if not result.get('ok'):
        raise ApiError('invalid_argument', str(result.get('error') or '恢复失败'))
    return ok({'products': result.get('products', 0), 'media': result.get('media', 0)})
