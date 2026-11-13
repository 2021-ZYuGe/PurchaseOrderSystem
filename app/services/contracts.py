# -*- coding: utf-8 -*-
"""合同生成服务：负责加载生成器、调用它、必要时落供应商档案。

生成器本身（模板填充规则）在 domain/contract_doc.py，这里只做编排。
"""
import importlib.util
import os

import app.config as config
from app.infra.logging import log
from app.services.archive import save_supplier

_gen_cache = {}


def load_generator():
    """按需加载生成器模块；源文件一改动就自动重载，不用重启服务"""
    src = str(config.CONTRACT_DOC_PATH)
    try:
        stamp = os.path.getmtime(src)
    except Exception:
        stamp = 0
    if _gen_cache.get('m') is None or _gen_cache.get('t') != stamp:
        try:
            spec = importlib.util.spec_from_file_location('gen_hetong', src)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        except Exception as e:
            log('加载生成器失败：%r' % (e,))
            if _gen_cache.get('m') is not None:
                return _gen_cache['m']          # 保留上一个可用版本
            raise
        _gen_cache['m'] = m
        _gen_cache['t'] = stamp
    return _gen_cache['m']


# 兼容旧名字
_load_gen = load_generator


def generate_contract(payload):
    """生成主合同；remember=True 时顺手把乙方信息存进档案"""
    gen = load_generator()
    res = gen.make_contract(payload)
    if payload.get('remember'):
        save_supplier(payload.get('party_b') or {})
    log('生成主合同: %s' % res.get('name'))
    return res


def generate_info_sheet(payload):
    """生成供应商信息收集表"""
    gen = load_generator()
    res = gen.make_info_sheet(payload)
    log('生成信息收集表: %s' % res.get('name'))
    return res
