# -*- coding: utf-8 -*-
"""产品、供应商目录的查询入口。"""
from app.infra.store import (  # noqa: F401
    catalog_meta,
    catalog_revision,
    get_catalog,
    known_contract_numbers,
    list_suppliers_light,
    normalize_path,
    product_count,
    search_products,
    search_suppliers,
)

__all__ = [
    'catalog_meta', 'catalog_revision', 'get_catalog', 'known_contract_numbers',
    'list_suppliers_light', 'normalize_path', 'product_count',
    'search_products', 'search_suppliers',
]
