# -*- coding: utf-8 -*-
"""供应商档案：把历史合同整理成续签时能直接带入的信息。

纯编排，不涉及 HTTP；所有数据来自 infra.store。
"""
import os
import re

from app.infra import store as sqlite_store
from app.infra.logging import log


def _norm_name(s):
    """供应商名归一化：括号全半角、空格、书名号都去掉"""
    s = str(s or '').strip()
    s = s.replace('（', '(').replace('）', ')')
    s = s.replace('　', '').replace(' ', '')
    s = s.replace('【', '').replace('】', '')
    return s


def _parse_money(s):
    m = re.search(r'([\d,]+(?:\.\d+)?)', str(s or ''))
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except Exception:
        return None


def _contract_dates():
    """合同号/文件名 -> 最近签署日期（来自 SQLite）"""
    dates = {}
    try:
        records = sqlite_store.get_contract_records()
    except Exception:
        return dates
    for r in records:
        ds = []
        if r.get('主合同日期'):
            ds.append(str(r['主合同日期']))
        ds += [str(x) for x in (r.get('签署日期') or []) if x]
        dt = max(ds) if ds else ''
        if not dt:
            continue
        for key in (r.get('合同号'), r.get('文件名')):
            if key:
                k = str(key)
                if dt > dates.get(k, ''):
                    dates[k] = dt
    return dates


def _last_order_amounts():
    """供应商 -> 最近一份合同的总金额

    金额优先从「付款方式」里的“本产品订单总金额为 X 元”取；
    没有这句话时，退回把该合同各产品行的「总金额」相加。
    """
    dates = _contract_dates()
    groups = {}
    try:
        recs = sqlite_store.get_historical_order_items()
    except Exception:
        return {}
    for r in recs:
        supplier = str(r.get('供应商') or '').strip()
        if not supplier:
            continue
        contract = str(r.get('合同号') or r.get('文件名') or '').strip()
        g = groups.setdefault((supplier, contract), {'amount': None, 'sum': 0.0, 'date': ''})
        pay = str(r.get('付款方式') or '')
        m = re.search(r'本产品订单总金额为\s*([\d,]+(?:\.\d+)?)\s*元', pay)
        if m and g['amount'] is None:
            try:
                g['amount'] = float(m.group(1).replace(',', ''))
            except Exception:
                pass
        amt = _parse_money(r.get('总金额'))
        if amt is not None:
            g['sum'] += amt
        dt = dates.get(contract) or dates.get(str(r.get('文件名') or '')) or ''
        if dt > g['date']:
            g['date'] = dt

    best = {}
    for (supplier, contract), g in groups.items():
        amount = g['amount'] if g['amount'] is not None else (g['sum'] or None)
        if amount is None:
            continue
        nk = _norm_name(supplier)
        rank = (g['date'] or '', contract)
        cur = best.get(nk)
        if cur is None or rank > cur[0]:
            best[nk] = (rank, amount, g['date'])
    return {k: {'amount': v[1], 'date': v[2]} for k, v in best.items()}


def load_archive():
    """从 SQLite 读取供应商档案（续签时自动带入旧信息用）"""
    try:
        d = sqlite_store.get_supplier_archive()
    except Exception:
        return {'suppliers': [], 'party_a': {}}
    sup = d.get('供应商') or []
    sup.sort(key=lambda x: x.get('最近签署日期') or '', reverse=True)
    # 甲方默认取最近模板里那套
    ja = d.get('甲方备选') or {}
    party_a = {}
    for n, v in ja.items():
        if '兴趣岛' in n:
            if (v.get('最近签署日期') or '') > (party_a.get('最近签署日期') or ''):
                party_a = v
    last_amounts = _last_order_amounts()
    last_keys = list(last_amounts.keys())
    light = []
    for s in sup:
        name = s.get('名称', '')
        item = {
            'name': name,
            'credit_code': s.get('统一社会信用代码', ''),
            'contact': s.get('联系人', ''),
            'tel': s.get('电话', ''),
            'email': s.get('邮箱', ''),
            'addr': s.get('地址', ''),
            'wechat': s.get('微信号', ''),
            'legal': s.get('法定代表人', ''),
            'bank_name': s.get('对公账户名') or name,
            'bank_account': s.get('对公账号', ''),
            'bank_open': s.get('开户行', ''),
            'last_sign': s.get('最近签署日期', ''),
        }
        nk = _norm_name(name)
        match = nk if nk and nk in last_amounts else None
        if not match and nk and '兴趣岛' not in nk:
            cands = [k for k in last_keys if nk.startswith(k) or k.startswith(nk)]
            if cands:
                # 优先公共前缀最长、长度差最小的，避免“甲公司”误配到别的公司
                match = max(cands, key=lambda k: (len(os.path.commonprefix([nk, k])), -abs(len(nk) - len(k))))
        if match:
            item['last_order_amount'] = last_amounts[match]['amount']
            item['last_order_date'] = last_amounts[match]['date']
        light.append(item)
    return {'suppliers': light, 'party_a': party_a}


def save_supplier(info):
    """新签或修改后写入 SQLite，空字段不会清除原有内容。"""
    try:
        return sqlite_store.save_supplier_profile(info or {})
    except Exception as e:
        log('保存供应商到 SQLite 失败: %r' % (e,))
        return False


def data_stamp():
    """SQLite 目录修订指纹：数据更新后页面可据此刷新。"""
    try:
        return sqlite_store.database_stamp()
    except Exception:
        return '0'

