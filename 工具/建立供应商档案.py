# -*- coding: utf-8 -*-
"""
建立「供应商档案」——从历史签署的合同里，自动抓取乙方的联系信息、银行账户。

为什么要做：
  续签旧供应商时，这些信息已经签过一次了，没必要再问对方要一遍。
  跑一次这个脚本，以后续签时下拉选中供应商，联系人/地址/电话/邮箱/公户信息全自动填满。

用法：双击运行，或命令行 python 建立供应商档案.py
产出：写入 data\\purchase.db；已有网页补录内容会保留，原 JSON 不再更新
"""
import io
import os
import re
import sys

from docx import Document

import sqlite_store

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
OUT = str(sqlite_store.DB_PATH)

# 常见的历史合同目录，逐个尝试
CANDIDATE_DIRS = [
    r'D:\合同审批附件',
    r'E:\合同',
    r'D:\合同',
]

FIELD_ALIAS = {
    '名称': ['供货单位（乙方）', '供货单位（乙方）:', '供货单位(乙方)', '乙方（供货方）', '乙方(供货方)',
             '供方（乙方）', '乙方名称', '开户名称', '对公账户', '账户名称', '公司名称'],
    '统一社会信用代码': ['统一社会信用代码', '纳税人识别号'],
    '联系人': ['联系人'],
    '电话': ['联系电话', '电话'],
    '邮箱': ['联系邮箱', '邮箱', '电子邮箱'],
    '地址': ['联系地址', '地址'],
    '微信号': ['微信号', '微信'],
    '法定代表人': ['法定代表人', '法人代表'],
    '对公账号': ['对公账号', '账　　号', '帐号', '账号'],
    '开户行': ['开户行', '开户银行'],
}

SIGNATURE_HINT = ('签署日期', '签订日期')


def norm(s):
    """去掉冒号空格等干扰"""
    return (s or '').replace('\u3000', '').replace(' ', '').replace(':', '').replace('：', '').strip()


def split_label_value(text):
    """把 '联系人：郑国麟' 拆成 ('联系人', '郑国麟')"""
    if not text:
        return None, None
    t = text.replace('\u3000', '').replace(' ', '')
    m = re.split(r'[：:]', t, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    return None, None


def match_field(label):
    """标签 -> 标准字段名"""
    if not label:
        return None
    low = label.replace(' ', '')
    # 先匹配长的别名，避免「联系电话」被「电话」抢先误伤同一批也没关系（都指向电话）
    for field, aliases in FIELD_ALIAS.items():
        for a in aliases:
            if low == a or low.startswith(a):
                return field
    return None


def clean_value(v):
    v = (v or '').strip()
    if v in ('/', '-', '——', '无', '无。'):
        return ''
    return v


def better_than(new, old):
    """非空、更长的优先"""
    if not new:
        return False
    if not old:
        return True
    return len(new) > len(old)


def merge(dst, src, src_rank):
    """把 src 里缺失的字段补进 dst；冲突时取 mtime 更新的一份"""
    for k, v in src.items():
        if k in ('来源', '最近签署日期', '_rank'):
            continue
        if not v:
            continue
        cur = dst.get(k)
        if not cur or better_than(v, cur):
            dst[k] = v
    # 日期取更晚的
    d = src.get('最近签署日期')
    if d:
        cur = dst.get('最近签署日期')
        if not cur or d > cur:
            dst['最近签署日期'] = d
            dst['来源'] = src.get('来源')


def extract_doc(path):
    """从一份合同里抽出甲方/乙方信息"""
    try:
        doc = Document(path)
    except Exception:
        return None, None

    jia, yi = {}, {}

    def put(bucket, field, value):
        value = clean_value(value)
        if not value or not field:
            return
        if not bucket.get(field) or len(value) > len(bucket[field]):
            bucket[field] = value

    # ---------- 表格：结构化信息 ----------
    for tb in doc.tables:
        for row in rows_safely(tb):
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 2:
                continue
            for ci, cell in enumerate(cells[:2]):
                # 单元格里可能是 "标签\n值"
                parts = [p for p in re.split(r'[\r\n]+', cell) if p.strip()]
                if len(parts) >= 2:
                    label, value = split_label_value(parts[-2] + parts[-1])
                    lab2, val2 = split_label_value(parts[0]), None
                    # 形如 "联系人：\n郑国麟"
                    l0, v0 = split_label_value(parts[0])
                    if l0 and not v0 and len(parts) > 1:
                        label, value = l0, parts[1]
                else:
                    label, value = split_label_value(parts[0] if parts else '')
                field = match_field(label)
                if not field:
                    continue
                bucket = jia if ci == 0 else yi
                put(bucket, field, value)

    # ---------- 段落：银行信息等 ----------
    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        # 签署日期
        if any(h in txt for h in SIGNATURE_HINT):
            m = re.search(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', txt)
            if m:
                d = '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
                if '最近签署日期' not in yi or d > yi['最近签署日期']:
                    yi['最近签署日期'] = d
        label, value = split_label_value(txt)
        field = match_field(label)
        if not field:
            continue
        # 段落里明确标甲方/乙方的，按标记归桶
        if '甲方' in (label or '') or '购货单位' in (label or ''):
            put(jia, field, value)
        else:
            put(yi, field, value)

    return jia, yi


def rows_safely(tb):
    try:
        return list(tb.rows)
    except Exception:
        return []


def _digits(s):
    return re.sub(r'\D', '', str(s or ''))


def _looks_bank(s):
    """看起来像银行名称"""
    s = str(s or '')
    return bool(re.search(r'银行|信用[社部]|银号|Bank', s)) and len(_digits(s)) < 8


def _looks_account(s):
    """看起来像银行账号（纯数字且够长）"""
    d = _digits(s)
    return len(d) >= 12 and not re.search(r'[一-龥]', str(s or ''))


# 甲方自己的标识：出现在任何字段里都说明抓错了，必须清掉
# （否则会把采购方的姓名/地址写进合同乙方栏，属于合同事故）
SELF_MARKERS = ('甲方公司', 'example', '示例公司', '张三')


def _clean_str(v):
    """去掉换行、不间断空格等脏字符"""
    v = str(v or '').replace('\xa0', ' ').replace('\u3000', ' ')
    v = re.sub(r'[\r\n\t]+', ' ', v)
    return v.strip()


def parse_embedded(cell_text, bucket):
    """有些合同的乙方格里是一整坨文本，如
       '示例科技有限公司\\n开户行：中国银行XX支行\\n账号：6222020000000000'
       这里把它拆开，各归各位。返回修正后的公司名称。"""
    parts = [p.strip() for p in re.split(r'[\r\n]+', str(cell_text or '')) if p.strip()]
    if not parts:
        return None
    company = _clean_str(parts[0])
    for p in parts[1:]:
        label, value = split_label_value(p)
        if not label:
            continue
        field = match_field(label)
        if not field:
            continue
        put_local(bucket, field, _clean_str(value))
    # 公司名只保留第一行，且去掉尾随的标签串
    company = re.split(r'(联系人|联系电话|联系邮箱|联系地址|开户行|账号|对公账号|统一社会信用代码)', company)[0]
    return _clean_str(company)


def put_local(bucket, field, value):
    value = clean_value(value)
    if not value or not field:
        return
    if not bucket.get(field) or len(value) > len(bucket[field]):
        bucket[field] = value


def sanitize_record(rec):
    """清理一条供应商档案：修复被污染的字段、剔除误抓的甲方信息"""
    # 1) 名称里混进了别的内容
    name = rec.get('名称') or ''
    if re.search(r'[\r\n]', name) or len(name) > 40:
        rec['名称'] = parse_embedded(name, rec)

    # 2) 所有字段去掉脏字符
    for k, v in list(rec.items()):
        if isinstance(v, str):
            rec[k] = _clean_str(v)

    # 3) 剔除误抓进来的甲方信息
    for k, v in list(rec.items()):
        if k in ('来源', '最近签署日期', '名称', '_rank'):
            continue
        if isinstance(v, str) and any(m in v for m in SELF_MARKERS):
            rec.pop(k, None)
    return rec


def fix_bank_fields(info):
    """纠正「开户行」和「对公账号」填反的情况。

    部分历史合同的表格里两个字段顺序不统一，导致账号写进了开户行、银行名写进了账号。
    这里按内容形态判断，强制归位。
    """
    bk = info.get('开户行') or ''
    ac = info.get('对公账号') or ''
    if not bk and not ac:
        return info
    if _looks_bank(bk) and _looks_account(ac):
        pass                      # 正常，不动
    elif _looks_account(bk) and _looks_bank(ac):
        info['开户行'], info['对公账号'] = ac, bk      # 明确填反，互换
    elif _looks_bank(bk) and not ac:
        info['对公账号'] = ''
    elif _looks_account(bk):
        # 只有开户行有值且像账号 → 它就是账号
        info['对公账号'] = info['对公账号'] or bk
        info['开户行'] = ''
    return info


def looks_like_company(name):
    return bool(name) and re.search(r'(公司|厂|店|中心|有限|合作社|工作室|研究院|集团|商行|经营部)', name) and len(name) >= 4


def main():
    # 命令行可指定目录
    dirs = sys.argv[1:] or [d for d in CANDIDATE_DIRS if os.path.isdir(d)]
    if not dirs:
        print('没有找到历史合同目录。请这样用：python 建立供应商档案.py "F:\\你的合同目录"')
        return

    files = []
    for d in dirs:
        for root, _dirs, fs in os.walk(d):
            for f in fs:
                if f.lower().endswith('.docx') and not f.startswith('~$'):
                    files.append(os.path.join(root, f))
    print('共发现 %d 份 docx，开始扫描…' % len(files))

    store = {}
    jia_store = {}
    ok = fail = 0
    for i, path in enumerate(files, 1):
        if i % 100 == 0:
            print('  已处理 %d / %d' % (i, len(files)))
        try:
            jia, yi = extract_doc(path)
        except Exception:
            fail += 1
            continue
        if not yi:
            fail += 1
            continue
        ok += 1
        name = clean_value(yi.get('名称') or '')
        # 名称兜底：从签署行 "甲方：X    乙方：Y" 里拿
        if not looks_like_company(name):
            continue
        yi['来源'] = path
        try:
            rank = os.path.getmtime(path)
        except Exception:
            rank = 0
        yi['_rank'] = rank
        key = name
        if key not in store:
            store[key] = dict(yi)
        else:
            merge(store[key], yi, rank)
        if jia.get('名称'):
            merge_jia(jia_store, jia)

    # 排序：最近签约的在前
    out_list = []
    for name, info in store.items():
        info.pop('_rank', None)
        info.setdefault('名称', name)
        info = sanitize_record(info)
        # 名称仍不像公司 → 丢弃，避免脏数据写进合同
        if not looks_like_company(info.get('名称')):
            continue
        fix_bank_fields(info)
        out_list.append(info)
    out_list.sort(key=lambda x: x.get('最近签署日期') or '', reverse=True)

    sqlite_store.ensure_database()
    added, updated = sqlite_store.merge_supplier_profiles(out_list, jia_store)

    full = sum(1 for x in out_list if x.get('电话') and x.get('地址') and x.get('对公账号'))
    total = len(sqlite_store.list_supplier_profiles())
    print('\n完成：成功解析 %d 份，跳过 %d 份' % (ok, fail))
    print('本次扫描 %d 家，其中信息较全（电话+地址+账号齐）%d 家' % (len(out_list), full))
    print('SQLite 档案：新增 %d 家，补全 %d 家，当前共 %d 家' % (added, updated, total))
    print('已写入：%s（原 JSON 保留为迁移备份，不再更新）' % OUT)


def merge_jia(store, jia):
    name = jia.get('名称')
    if not name:
        return
    if name not in store:
        store[name] = dict(jia)
    else:
        for k, v in jia.items():
            if v and (not store[name].get(k) or len(v) > len(store[name][k])):
                store[name][k] = v


def _utf8_console():
    """仅命令行直接运行时才需要；被别的脚本 import 时绝不能动全局 stdout"""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


if __name__ == '__main__':
    _utf8_console()
    main()
