# -*- coding: utf-8 -*-
"""供应商档案、合同期限与到期视图。"""
from app.infra.store import (  # noqa: F401
    contract_expiry_overview,
    delete_contract_term,
    expiry_bucket,
    get_supplier_archive,
    list_supplier_profiles,
    merge_supplier_profiles,
    save_contract_term,
    save_supplier_profile,
    supplier_contract_stats,
)

__all__ = [
    'contract_expiry_overview', 'delete_contract_term', 'expiry_bucket',
    'get_supplier_archive', 'list_supplier_profiles', 'merge_supplier_profiles',
    'save_contract_term', 'save_supplier_profile', 'supplier_contract_stats',
]
