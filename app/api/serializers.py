# -*- coding: utf-8 -*-
"""把内部数据（历史遗留的中文键）翻译成对外的英文结构。

数据库列名本来就是英文，只有产品/供应商/到期视图沿用了中文键。
翻译集中在这里，services 与 infra 不需要为接口改名。
"""

PROFILE_FIELDS = {
    '名称': 'name',
    '统一社会信用代码': 'credit_code',
    '联系人': 'contact',
    '电话': 'tel',
    '邮箱': 'email',
    '地址': 'addr',
    '微信号': 'wechat',
    '法定代表人': 'legal',
    '对公账户名': 'bank_name',
    '对公账号': 'bank_account',
    '开户行': 'bank_open',
    '最近签署日期': 'last_sign',
    '来源': 'source',
}


def product(item):
    image = item.get('图片') or ''
    images = []
    if image:
        images.append(image)
    for name in item.get('备选图片') or []:
        if name and name not in images:
            images.append(name)
    return {
        'id': item.get('id', ''),
        'name': item.get('产品名称', ''),
        'spec': item.get('规格', ''),
        'image': image,
        'images': images,
        'suppliers': item.get('供应商') or [],
        'prices': item.get('历史单价') or [],
        'categories': item.get('分类') or [],
        'aliases': item.get('别名') or [],
        'order_count': int(item.get('下单次数') or 0),
    }


def supplier(item):
    return {
        'id': item.get('id', ''),
        'name': item.get('供应商名称', ''),
        'phone': item.get('电话', ''),
        'latest_sign_date': item.get('最近签约日期', ''),
        'main_contract_date': item.get('主合同日期', ''),
        'latest_contract_no': item.get('最近合同号', ''),
        'contract_count': int(item.get('合同记录数') or 0),
        'history_contract_count': int(item.get('历史合同份数') or 0),
        'product_ids': item.get('产品keys') or [],
    }


def profile(item):
    return {PROFILE_FIELDS.get(key, key): value for key, value in item.items()}


def term(item):
    return {
        'supplier': item.get('供应商', ''),
        'start_date': item.get('起始日', ''),
        'end_date': item.get('到期日', ''),
    }


def expiry_item(item):
    return {
        'supplier': item.get('供应商', ''),
        'end_date': item.get('到期日', ''),
        'start_date': item.get('起始日', ''),
        'days_left': item.get('剩余天数'),
        'bucket': item.get('档位', ''),
        'bucket_label': item.get('档位名', ''),
        'contract_no': item.get('合同号', ''),
        'contract_file': item.get('合同文件', ''),
        'source': item.get('来源', ''),
        'note': item.get('备注', ''),
        'pending': bool(item.get('待确认')),
        'last_sign_date': item.get('最近签约', ''),
        'contract_count': int(item.get('合同份数') or 0),
    }


def expiry(data):
    return {
        'today': data.get('today', ''),
        'total': data.get('total', 0),
        'counts': data.get('counts') or {},
        'buckets': data.get('buckets') or [],
        'items': [expiry_item(item) for item in data.get('items') or []],
    }


def freshness(data):
    return {
        'data_updated_at': data.get('数据更新时间', ''),
        'last_import': data.get('最近导入', ''),
        'contract_records': data.get('合同记录', 0),
        'imported_files': data.get('已收录文件', 0),
        'last_sign_date': data.get('最近落款', ''),
        'last_main_contract_date': data.get('最近主合同', ''),
    }


def pending(data):
    return {
        'checked_dirs': data.get('已检查目录') or [],
        'missing_dirs': data.get('不可用目录') or [],
        'pending_count': data.get('待导入数量', 0),
        'newest_file': data.get('最新文件', ''),
        'newest_date': data.get('最新日期', ''),
        'samples': data.get('待导入样例') or [],
        'checked_at': data.get('检查时间', ''),
    }
