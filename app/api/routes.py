# -*- coding: utf-8 -*-
"""API 路由表：path -> 服务调用。

这里只做参数取值和返回结构，业务在 services/，数据在 infra/。
返回结构（{'ok':..., 'data':...} / {'ok': False, 'error': ...}）必须与重构前一致，
前端不感知本次改造。
"""
import io
import sys
import traceback

from app.infra import store as sqlite_store
from app.infra.logging import log
from app.services import archive as archive_service
from app.services import contracts as contract_service
from app.services import sync as sync_service

# GET 也允许的只读接口（其余接口只接受 POST）
GET_PATHS = (
    '/api/meta',
    '/api/bootstrap',
    '/api/products',
    '/api/suppliers',
    '/api/contract_status',
    '/api/sync_status',
    '/api/contract_expiry',
)


def dispatch(path, payload=None):
    p = payload if isinstance(payload, dict) else {}
    try:
        if path == '/api/meta':
            return {'ok': True, 'data': sqlite_store.catalog_meta()}

        if path == '/api/bootstrap':
            # 首屏一次拿齐：统计 + 轻量供应商列表；产品改按需搜索
            return {'ok': True, 'data': {
                'meta': sqlite_store.catalog_meta(),
                'suppliers': sqlite_store.list_suppliers_light(),
            }}

        if path == '/api/products':
            q = p.get('q') or p.get('query') or ''
            try:
                limit = int(p.get('limit') or 20)
            except (TypeError, ValueError):
                limit = 20
            return {'ok': True, 'data': {
                'items': sqlite_store.search_products(q, p.get('supplier') or None, limit),
            }}

        if path == '/api/suppliers':
            return {'ok': True, 'data': {
                'items': sqlite_store.search_suppliers(p.get('q') or ''),
            }}

        if path == '/api/archive':
            return {'ok': True, 'data': archive_service.load_archive()}

        if path == '/api/make_contract':
            return contract_service.generate_contract(p)

        if path == '/api/make_info_sheet':
            return contract_service.generate_info_sheet(p)

        if path == '/api/contract_status':
            # 数据新鲜度 + 来源目录里还没导入的合同
            return {'ok': True, 'data': {
                'freshness': sqlite_store.data_freshness(),
                'pending': sqlite_store.scan_pending_contracts(),
            }}

        if path == '/api/contract_expiry':
            return {'ok': True, 'data': sqlite_store.contract_expiry_overview()}

        if path == '/api/save_contract_term':
            res = sqlite_store.save_contract_term(
                p.get('供应商') or p.get('supplier') or '',
                p.get('起始日') or p.get('start') or '',
                p.get('到期日') or p.get('end') or '',
                p.get('备注') or p.get('note') or '',
            )
            log('登记合同期限：%s 至 %s' % (res.get('供应商'), res.get('到期日')))
            return {'ok': True, 'data': res,
                    'overview': sqlite_store.contract_expiry_overview()}

        if path == '/api/delete_contract_term':
            res = sqlite_store.delete_contract_term(p.get('供应商') or p.get('supplier') or '')
            log('撤销合同期限登记：%s' % res.get('供应商'))
            return {'ok': True, 'data': res,
                    'overview': sqlite_store.contract_expiry_overview()}

        if path == '/api/sync_contracts':
            return sync_service.start()

        if path == '/api/sync_status':
            return {'ok': True, 'data': sync_service.status()}

        if path == '/api/save_supplier':
            return {'ok': archive_service.save_supplier(p or {})}

        return {'ok': False, 'error': '未知接口 ' + path}
    except Exception as e:
        try:
            log('接口异常 %s: %r\n%s' % (path, e, traceback.format_exc()))
        except Exception:
            pass
        return {'ok': False, 'error': '%s' % e}
    finally:
        # 生成器里若有人改动 sys.stdout，这里把它恢复到可用状态，避免后续日志写坏
        try:
            if getattr(sys, 'stdout', None) is None or getattr(sys.stdout, 'closed', False):
                sys.stdout = io.StringIO()
        except Exception:
            pass
