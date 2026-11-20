# -*- coding: utf-8 -*-
"""目录：产品、供应商、档案。"""
from flask import request

from app.api import serializers
from app.api.responses import ApiError, ok
from app.infra.repositories import catalog as catalog_repo
from app.infra.repositories import suppliers as supplier_repo


def meta():
    return ok(catalog_repo.catalog_meta())


def products():
    query = request.args.get('q', '')
    supplier = request.args.get('supplier') or None
    try:
        limit = max(1, min(100, int(request.args.get('limit') or 20)))
    except ValueError:
        limit = 20
    items = catalog_repo.search_products(query, supplier, limit)
    return ok({'items': [serializers.product(item) for item in items]})


def suppliers():
    items = catalog_repo.search_suppliers(request.args.get('q', ''))
    return ok({'items': [serializers.supplier(item) for item in items]})


def archive_get():
    data = supplier_repo.get_supplier_archive()
    profiles = [serializers.profile(item) for item in data.get('供应商') or []]
    name = (request.args.get('name') or '').strip()
    if name:
        profiles = [item for item in profiles if item.get('name') == name]
    return ok({'profiles': profiles, 'party_a': data.get('甲方备选') or {}})


def archive_save():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name') or '').strip()
    if not name:
        raise ApiError('invalid_argument', '供应商名称不能为空')
    supplier_repo.save_supplier_profile(body)
    return ok({'saved': True})


PARTY_A_FIELDS = ('short', 'credit_code', 'contact', 'tel', 'email', 'addr', 'active')


def party_a_list():
    return ok({'items': supplier_repo.list_party_a()})


def party_a_save():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name') or '').strip()
    if not name:
        raise ApiError('invalid_argument', '甲方名称不能为空')
    payload = {key: body.get(key) for key in PARTY_A_FIELDS if key in body}
    if 'active' in payload:
        payload['active'] = bool(payload['active'])
    return ok(supplier_repo.save_party_a(name, payload))


def duplicates():
    return ok({'items': supplier_repo.supplier_duplicate_candidates()})


def merge():
    body = request.get_json(silent=True) or {}
    source = str(body.get('source') or '').strip()
    target = str(body.get('target') or '').strip()
    if not source or not target:
        raise ApiError('invalid_argument', '请选择要合并的两个供应商')
    try:
        return ok(supplier_repo.merge_suppliers(source, target))
    except ValueError as exc:
        raise ApiError('invalid_argument', str(exc))
