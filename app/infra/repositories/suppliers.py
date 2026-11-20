# -*- coding: utf-8 -*-
"""供应商档案、合同期限与到期视图。"""
from app.infra.store import (  # noqa: F401
    contract_expiry_overview,
    delete_contract_term,
    expiry_bucket,
    get_supplier_archive,
    list_party_a,
    list_supplier_profiles,
    merge_supplier_profiles,
    merge_suppliers,
    save_contract_term,
    save_party_a,
    save_supplier_profile,
    supplier_contract_stats,
    supplier_duplicate_candidates,
)

__all__ = [
    'contract_expiry_overview', 'delete_contract_term', 'expiry_bucket',
    'get_supplier_archive', 'list_party_a', 'list_supplier_profiles',
    'merge_supplier_profiles', 'merge_suppliers', 'save_contract_term',
    'save_party_a', 'save_supplier_profile', 'supplier_contract_stats',
    'supplier_duplicate_candidates',
]
