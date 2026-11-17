# -*- coding: utf-8 -*-
"""合同：期限、到期视图、生成主合同与信息表。"""
from flask import request

from app.api import serializers
from app.api.responses import ApiError, ok
from app.infra.repositories import contracts as contract_repo
from app.infra.repositories import suppliers as supplier_repo
from app.services import contracts as contract_service


def expiry():
    return ok(serializers.expiry(supplier_repo.contract_expiry_overview()))


def save_term():
    body = request.get_json(silent=True) or {}
    try:
        result = supplier_repo.save_contract_term(
            body.get('supplier') or body.get('供应商') or '',
            body.get('start_date') or '',
            body.get('end_date') or '',
            body.get('note') or '',
        )
    except ValueError as exc:
        raise ApiError('invalid_argument', str(exc))
    return ok({'term': serializers.term(result),
               'overview': serializers.expiry(supplier_repo.contract_expiry_overview())})


def delete_term():
    name = (request.args.get('supplier') or '').strip()
    try:
        result = supplier_repo.delete_contract_term(name)
    except ValueError as exc:
        raise ApiError('invalid_argument', str(exc))
    return ok({'term': serializers.term(result),
               'overview': serializers.expiry(supplier_repo.contract_expiry_overview())})


def status():
    return ok({
        'freshness': serializers.freshness(contract_repo.data_freshness()),
        'pending': serializers.pending(contract_repo.scan_pending_contracts()),
    })


def _result(payload):
    result = payload or {}
    if result.get('ok') is False:
        message = str(result.get('error') or '生成失败')
        code = 'template_missing' if '模板' in message else 'invalid_argument'
        raise ApiError(code, message)
    return result


def generate():
    body = request.get_json(silent=True) or {}
    if not body:
        raise ApiError('invalid_argument', '请求体为空')
    return ok(_result(contract_service.generate_contract(body)))


def info_sheet():
    body = request.get_json(silent=True) or {}
    party_b = body.get('party_b') if isinstance(body.get('party_b'), dict) else body
    if not party_b:
        raise ApiError('invalid_argument', '缺少乙方信息')
    return ok(_result(contract_service.generate_info_sheet({'party_b': party_b})))
