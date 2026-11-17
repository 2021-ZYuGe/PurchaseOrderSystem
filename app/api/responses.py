# -*- coding: utf-8 -*-
"""统一响应信封与业务异常。"""
from flask import jsonify


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def ok(data=None, status=200):
    return jsonify({'ok': True, 'data': data}), status


def fail(code, message, status=400):
    return jsonify({'ok': False, 'error': {'code': code, 'message': message}}), status
