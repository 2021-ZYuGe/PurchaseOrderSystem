# -*- coding: utf-8 -*-
"""供应商与甲方名称的统一归一：全半角、空白、标签截断都在这里。"""
import re
import unicodedata

# 合同里跟在公司名后面的字段，遇到就截断
CUT_LABELS = (
    '联系人', '联系电话', '电话', '联系地址', '地址', '统一社会信用代码', '统一社会',
    '开户', '盖章', '签章', '签署日期', '日期', '邮箱', '微信', '法定代表人',
)

# 目前签约的两家甲方；甲方信息以后端 party_a_profiles 为准，这里只用于解析识别
PARTY_A_NAMES = (
    '广州兴趣岛信息科技有限公司',
    '广州普惠优品电子商贸有限公司',
)
PARTY_A_LABELS = ('购货单位', '甲方', '发包方', '发包单位', '采购方', '需方')


def name_key(value):
    """同一家公司的判断键：全角转半角、去空白、去书名号、忽略大小写。"""
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = re.sub(r'\s+', '', text)
    text = text.replace('《', '').replace('》', '')
    text = text.replace('【', '').replace('】', '')
    return text.strip('"\'“”‘’').lower()


def clean_supplier_name(value):
    """把合同单元格里的原始文字收成公司名：按标签截断，去掉内部空白。"""
    text = unicodedata.normalize('NFKC', str(value or ''))
    text = text.replace('\u3000', ' ').replace('\r', ' ').replace('\n', ' ')
    for label in CUT_LABELS:
        index = text.find(label)
        if index > 0:
            text = text[:index]
    text = re.sub(r'\s+', '', text)
    return text.strip('：:，,。;；、')
