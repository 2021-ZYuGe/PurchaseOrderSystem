# -*- coding: utf-8 -*-
"""
主合同生成器 —— 用法务原件做底稿，只往里填信息，格式 100% 保留

支持三种产出：
  1. make_contract()  新签 / 续签的主合同（含附件1反商业贿赂 + 附件2订购清单）
  2. make_info_sheet() 供应商信息收集表（发给对方填）
"""
import io
import os
import re
import sys
import urllib.parse
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

if __package__ in (None, ''):                 # 允许直接 python app/domain/contract_doc.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import OUT_DIR, TPL_DIR

def _utf8_console():
    """仅命令行直接运行时才需要；被服务器 import 时绝不能动全局 stdout"""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))      # app/domain/

# 法务模板位置
# 批采已换成《购销框架合同（集采模式）》；旧版留在 合同模板/历史版本/ 里备查。
# 注意：不要再挂 E 盘旧模板做兜底，否则项目内模板丢失时会悄悄生成旧版合同。
TPL_SOURCE = {
    'batch': [
        os.path.join(TPL_DIR, '主合同-一次性发货.docx'),
    ],
    'dropship': [
        r'E:\bing\采购合同模版\0703【罚则优化】【购销框架合同】【一件代发】-20260703.docx',
        os.path.join(TPL_DIR, '主合同-一件代发.docx'),
    ],
    'simple': [
        os.path.join(TPL_DIR, '主合同-单次简易版.docx'),
    ],
}

# 合同类型 -> 模板文件名（都放在 合同模板/ 下）
TPL_FILES = {
    'batch': '主合同-一次性发货.docx',
    'dropship': '主合同-一件代发.docx',
    'simple': '主合同-单次简易版.docx',
}

# 合同类型 -> 中文名（报错时给人看，不要把 batch 这种内部代号丢到页面上）
TPL_NAMES = {
    'batch': '批采（一次性发货）',
    'dropship': '一件代发',
    'simple': '单次简易版',
}

# 默认值（和现有习惯一致，页面上都能改）
DEFAULTS = {
    'tax_rate': '13%',
    'invoice_type': '专票',        # 专票 / 普票（历史合同里多数为专票）
    'invoice_days': '15',
    'pay_days': '15',
    'delivery_days': '10',
    'reconcile_days': '2',
    'years': '1',
    'place': '广州市天河区',
    # 一件代发专用：同一结算周期内无效发货订单占比阈值
    # 421 份历史合同无人填过，属商务判断，页面上可改，默认取 5%
    'invalid_order_pct': '5',
}

INVALID = r'[\\/:*?"<>|\r\n\t]'


# ---------------- 基础工具 ----------------
def ensure_tpl(kind):
    """找到模板：优先用项目内 合同模板/ 下的文件，缺了才按 TPL_SOURCE 兜底"""
    if kind not in TPL_FILES:
        raise ValueError('未知合同类型：%s' % kind)
    local = os.path.join(TPL_DIR, TPL_FILES[kind])
    if os.path.exists(local):
        return local
    for src in TPL_SOURCE[kind]:
        if os.path.exists(src):
            os.makedirs(TPL_DIR, exist_ok=True)
            import shutil
            shutil.copy2(src, local)
            return local
    # 报错要能直接照着修：说清缺哪个文件、应该放在哪。
    # 另一台电脑上装系统时最常见的就是「合同模板」文件夹没一起拷过去。
    raise FileNotFoundError(
        '找不到「%s」合同模板，缺少文件 %s。'
        '请把整个「合同模板」文件夹复制到程序目录下（应放位置：%s）'
        % (TPL_NAMES.get(kind, kind), TPL_FILES[kind], TPL_DIR)
    )


def safe_name(s, limit=40):
    s = re.sub(INVALID, '', str(s or '')).strip()
    return s[:limit]


def _first_run_fmt(para):
    """把段落所有文字塞进第一个 run，保留首 run 的格式"""
    runs = para.runs
    if not runs:
        return None
    head = runs[0]
    for r in list(runs[1:]):
        r._element.getparent().remove(r._element)
    return head


def set_text(para, text):
    """整段替换文字，尽量保留字体格式"""
    head = _first_run_fmt(para)
    if head is None:
        para.add_run(text)
        return
    head.text = text


def append_text(para, text, src_run=None):
    """在段落末尾追加文字，继承原有 run 的字体"""
    if not text:
        return
    r = para.add_run(text)
    src = src_run or (para.runs[-2] if len(para.runs) >= 2 else None)
    if src is not None:
        srcPr = src._element.find(qn('w:rPr'))
        if srcPr is not None:
            dst = r._element.get_or_add_rPr()
            for c in list(dst):
                dst.remove(c)
            for c in srcPr:
                dst.append(deepcopy(c))
    return r


def rep(para, old, new, limit=1):
    """段落内替换（先试单 run，再退化为整段重建）"""
    if old not in para.text:
        return False
    n = 0
    for r in para.runs:
        if old in r.text:
            r.text = r.text.replace(old, new, 1)
            n += 1
            if n >= limit:
                return True
    # 跨 run
    set_text(para, para.text.replace(old, new, limit))
    return True


def rep_re(para, pattern, new, count=1):
    """段落内正则替换（先试单 run，再退化为整段重建）"""
    for r in para.runs:
        t = re.sub(pattern, new, r.text, count=count)
        if t != r.text:
            r.text = t
            return True
    txt = para.text
    t = re.sub(pattern, new, txt, count=count)
    if t == txt:
        return False
    set_text(para, t)
    return True


def _copy_run_fmt(src, dst):
    """把 src 的字体格式复制给 dst"""
    srcPr = src._element.find(qn('w:rPr'))
    if srcPr is None:
        return
    d = dst._element.get_or_add_rPr()
    for c in list(d):
        d.remove(c)
    for c in srcPr:
        d.append(deepcopy(c))


def _append_value(para, value, bold=False):
    """在标签后面追加值：先清掉标签后的空白，再补一个不带空格的 run

    合同模板里「购货单位（甲方）：            」这种留白很常见，
    直接 append 会把名字顶到很远，所以先把尾部空白削掉。
    """
    value = str(value or '').strip()
    if not value:
        return
    runs = para.runs
    src = runs[-1] if runs else None
    if src is not None:
        t = src.text.rstrip(' \t\xa0')
        if t != src.text:
            src.text = t
            if not t:
                src._element.getparent().remove(src._element)
                src = para.runs[-1] if para.runs else None
    r = para.add_run(value)
    if src is not None:
        _copy_run_fmt(src, r)
    r.bold = bool(bold)


def _set_labeled(para, label, value):
    """把「标签：旧值」更新为「标签：新值」，模板里已有值也不会重复追加

    新集采模板的甲方信息是预填在表格里的，旧的 append 方式会把公司名
    再写一遍，变成「广州兴趣岛…广州兴趣岛…」。
    """
    txt = para.text
    if not txt.startswith(label):
        return False
    value = str(value or '').strip()
    if not value:
        return True                     # 页面没填就保留模板原值
    cur = txt[len(label):].strip()
    if cur == value:
        return True
    if cur:
        rep(para, cur, value)
    else:
        _append_value(para, value)
    return True


def _disp_width(s):
    """按 Word 里的显示宽度估算：中文算 2，英文/数字算 1"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(s or ''))


def fill_brackets(para, values):
    """按顺序把段落里的【】/【 】逐个填上值

    必须严格按段落里的先后顺序替换。Word 经常把第一个占位符拆成
    '【' + ' ' + '】' 三个 run，而后面某个占位符是完整的 '【】'；
    如果按 run 逐个找，会先填后面那个，导致年月日错位。
    """
    for v in values:
        txt = para.text
        m = re.search(r'【\s*】', txt)
        if not m:
            break
        pos, done = 0, False
        for r in para.runs:
            start, end = pos, pos + len(r.text)
            if start <= m.start() < end:
                # 占位符必须完整落在这一个 run 里，才能保留它的字体格式
                if m.end() <= end:
                    a, b = m.start() - start, m.end() - start
                    r.text = r.text[:a] + str(v) + r.text[b:]
                    done = True
                break
            pos = end
        if not done:
            set_text(para, txt[:m.start()] + str(v) + txt[m.end():])


TODO_IGNORE = (
    '本次产品订购的总费用',      # 订单金额，每次下单时才确定，本就该留空
)


def collect_todo(doc):
    """清点文档里剩下的空占位符，回给页面提示用户手动补"""
    seen, out = set(), []
    blocks = list(doc.paragraphs)
    for tb in doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                blocks.extend(cell.paragraphs)
    for para in blocks:
        raw = para.text.strip()
        if not raw or ('【' not in raw):
            continue
        if any(k in raw for k in TODO_IGNORE):
            continue
        hit = False
        for token in ('【】', '【 】', '【 %】', '【%】'):
            if token in raw:
                hit = True
        if not hit:
            continue
        key = raw[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(raw[:90])
    return out


def date_parts(iso):
    dt = datetime.strptime(iso[:10], '%Y-%m-%d')
    return dt.year, dt.month, dt.day


def end_date(iso, years):
    """合同期限止日：起算日 + N 年 - 1 天

    例：2026-11-04 起 1 年，止日应为 2027-11-03，而不是 2027-11-04。
    """
    y, m, d = date_parts(iso)
    try:
        end = datetime(y + int(years), m, d)
    except ValueError:
        end = datetime(y + int(years), m, 28)
    return end - timedelta(days=1)


def add_days(iso, days):
    """签约日 + N 个自然日（集采模板的交货时间要填具体日期）"""
    try:
        n = int(str(days).strip())
    except Exception:
        n = int(DEFAULTS['delivery_days'])
    return datetime.strptime(iso[:10], '%Y-%m-%d') + timedelta(days=n)


def clear_yellow(doc):
    """清掉法务模板里用来标记待填项的黄色底纹

    集采模板有 81 处黄色高亮（日期、账号、甲方抬头等）。填完值如果不清，
    正式合同上会留一片黄底，像没填完的草稿。
    """
    for h in list(doc.element.body.iter(qn('w:highlight'))):
        if h.get(qn('w:val')) == 'yellow':
            h.getparent().remove(h)


CN_DIGITS = '零壹贰叁肆伍陆柒捌玖'
CN_UNITS = ('', '拾', '佰', '仟')
CN_BIG = ('', '万', '亿', '兆')


def clean_amount(v):
    """把页面传来的金额清成纯数字字符串；不合法返回空"""
    s = str(v or '').strip().replace(',', '').replace('，', '')
    s = s.replace('¥', '').replace('￥', '').replace('元', '')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', s):
        return ''
    try:
        if float(s) <= 0:
            return ''
    except Exception:
        return ''
    if '.' in s:
        a, b = s.split('.', 1)
        b = (b + '00')[:2]
        s = a if b == '00' else a + '.' + b
    return s


def _cn_section(n):
    """0 < n < 10000 的中文大写"""
    s, zero = '', False
    for i in range(3, -1, -1):
        d = (n // (10 ** i)) % 10
        if d == 0:
            if s:
                zero = True
        else:
            if zero:
                s += '零'
                zero = False
            s += CN_DIGITS[d] + CN_UNITS[i]
    return s


def amount_to_cn(v):
    """人民币金额转大写，例如 12500.50 -> 壹万贰仟伍佰元伍角"""
    s = str(v or '').strip().replace(',', '').replace('，', '')
    try:
        num = float(s)
    except Exception:
        return ''
    if num <= 0 or num >= 10 ** 12:
        return ''
    integer = int(num)
    frac = int(round((num - integer) * 100))
    if frac >= 100:
        integer += 1
        frac = 0
    if integer == 0:
        head = '零'
    else:
        sections, n = [], integer
        while n > 0:
            sections.append(n % 10000)
            n //= 10000
        parts = []
        for idx in range(len(sections) - 1, -1, -1):
            sec = sections[idx]
            if sec == 0:
                if parts and not parts[-1].endswith('零'):
                    parts.append('零')
                continue
            if parts and sec < 1000 and not parts[-1].endswith('零'):
                parts.append('零')
            parts.append(_cn_section(sec) + CN_BIG[idx])
        head = ''.join(parts).rstrip('零') or '零'
    res = head + '元'
    if frac == 0:
        return res + '整'
    jiao, fen = divmod(frac, 10)
    if jiao:
        res += CN_DIGITS[jiao] + '角'
    if fen:
        res += CN_DIGITS[fen] + '分'
    return res


SIMPLE_CONTACT = (
    ('联系人：', 'contact'),
    ('联系电话：', 'tel'),
    ('联系邮箱：', 'email'),
    ('联系地址：', 'addr'),
)


def _fill_simple_contact(para, src):
    """单次简易版的联系信息是普通段落，不是表格

    而且乙方的「联系电话 / 联系邮箱」在同一段的两行里，不能只按段首标签填，
    这里按行拆开逐行处理。
    """
    lines = para.text.split('\n')
    out, changed = [], False
    for line in lines:
        s = line.strip()
        hit = False
        for label, key in SIMPLE_CONTACT:
            if s.startswith(label):
                v = str(src.get(key) or '').strip()
                out.append((s[:len(label)] + v) if v else line)
                changed = changed or bool(v)
                hit = True
                break
        if not hit:
            out.append(line)
    if changed:
        set_text(para, '\n'.join(out))


def _money(v):
    try:
        return '{:,.2f}'.format(float(v))
    except Exception:
        return str(v)


def _pay_clause(t, amount):
    """按付款方式生成结算条款：full / p30 / p50"""
    mode = str(t.get('pay_mode') or 'full').strip()
    rate = str(t.get('tax_rate') or '13%').strip()
    if rate and not rate.endswith('%'):
        rate += '%'
    inv = '普通' if str(t.get('invoice_type') or '专票').strip() == '普票' else '专用'
    invoice = '%s增值税%s发票' % (rate or '13%', inv)
    total = _money(amount)

    if mode == 'p30':
        pre = float(amount) * 0.3
        rest = float(amount) - pre
        return ('本产品订单总金额为%s元，甲方签订合同后10个工作日内向乙方支付30%%预付款，即%s元。'
                '乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，'
                '甲方收到通知后支付剩余尾款%s元。'
                '乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的%s。'
                % (total, _money(pre), _money(rest), invoice))

    if mode == 'p50':
        pre = float(amount) * 0.5
        rest = float(amount) - pre
        return ('本产品订单总金额为%s元，甲方签订合同后10个工作日内向乙方支付50%%预付款，即%s元。'
                '乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，'
                '甲方收到通知后支付剩余尾款%s元。'
                '乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的%s。'
                % (total, _money(pre), _money(rest), invoice))

    return ('本产品订单总金额为%s元，签订本产品订购清单，并经甲乙双方确认当次甲方应付金额后，'
            '甲方应及时向乙方付款。乙方应在甲方支付全部款项后7个工作日内向甲方开具等额合法有效的%s。'
            % (total, invoice))


def _fill_simple_settlement(para, t):
    """单次简易版结算句：

    有订单金额时按所选付款方式整段生成；没有金额时保留原占位符填法。
    """
    amount = clean_amount(t.get('order_amount'))
    if amount:
        set_text(para, '结算方式：' + _pay_clause(t, amount) + '乙方指定收款银行账号如下：')
        return
    rate = str(t.get('tax_rate') or '').strip()
    if rate and not rate.endswith('%'):
        rate += '%'
    inv = '普通' if str(t.get('invoice_type') or '专票').strip() == '普票' else '专用'
    inv_days = str(t.get('invoice_days') or '').strip()
    pay_days = str(t.get('pay_days') or '').strip()
    if inv_days:
        rep(para, '签订后【】个工作日', '签订后%s个工作日' % inv_days)
    if rate:
        rep(para, '税率为【】%', '税率为%s' % rate)
    rep(para, '增值税【专用/普通】发票', '增值税%s发票' % inv)
    if pay_days:
        rep(para, '发票后【】个工作日', '发票后%s个工作日' % pay_days)


# ---------------- 主合同 ----------------
def make_contract(p):
    """p: 前端送来的字段字典 -> 返回 {'url','name','path'}"""
    kind = p.get('contract_type', 'batch')
    tpl = ensure_tpl(kind)
    doc = Document(tpl)

    a = dict(p.get('party_a') or {})
    if not (a.get('name') or '').strip():
        a['name'] = '广州兴趣岛信息科技有限公司'
    b = p.get('party_b') or {}
    sign = p.get('sign') or {}
    t = dict(DEFAULTS)
    t.update({k: v for k, v in (p.get('terms') or {}).items() if v not in (None, '')})
    # 合同期限在页面上是 sign.years，不在 terms 里；以前只读 DEFAULTS，页面改年限不生效
    if str(sign.get('years') or '').strip():
        t['years'] = str(sign['years']).strip()

    today = sign.get('date') or datetime.now().strftime('%Y-%m-%d')
    y, m, d = date_parts(today)
    ey, em, ed = end_date(today, t['years']).year, end_date(today, t['years']).month, end_date(today, t['years']).day
    place = sign.get('place') or DEFAULTS['place']

    b_name = (b.get('name') or '').strip()
    a_name = (a.get('name') or '广州兴趣岛信息科技有限公司').strip()
    amount = clean_amount(t.get('order_amount'))
    amount_cn = amount_to_cn(amount) if amount else ''

    # ---- 1) 逐段替换 ----
    simple_party = None      # 单次简易版：当前这段联系信息属于甲方还是乙方
    for para in doc.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue

        # 首部签署日期 + 地点（框架合同写「在合作期内」，简易版没有这几个字）
        if '于【】年【】月【】日' in txt and '达成如下' in txt:
            fill_brackets(para, [y, m, d])
            if place != DEFAULTS['place']:
                rep(para, '在广州市天河区', '在%s' % place)
            continue

        # 合同期限 + 起止
        if '本合同期限为【】' in txt or ('本合同期限为' in txt and '【】' in txt):
            fill_brackets(para, [t['years'], y, m, d, ey, em, ed])
            rep(para, '%s 年' % t['years'], '%s年' % t['years'])   # 模板「【】 年」多一个空格
            rep(para, '自 %s年' % y, '自%s年' % y)                 # 模板「自 【】年」多一个空格
            # 法务模板原文是「自【】年【】月【】起至【】年【】月【】止」，漏了「日」，
            # 不补会生成「2026年11月4起」，这里只补这一个字，不改其他表述。
            rep(para, '%s月%s起' % (m, d), '%s月%s日起' % (m, d))
            rep(para, '%s月%s止' % (em, ed), '%s月%s日止' % (em, ed))
            continue

        # 银行账户
        if txt.startswith('对公账户：') or txt.rstrip().endswith('对公账户：'):
            _append_value(para, b_name)
            continue
        if txt.startswith('对公账号：') or txt.rstrip().endswith('对公账号：'):
            _append_value(para, (b.get('bank_account') or '').strip())
            continue
        if txt.startswith('开户行：') or txt.rstrip().endswith('开户行：'):
            _append_value(para, (b.get('bank_open') or '').strip())
            continue
        # 单次简易版：开户账号 / 开户名称
        if kind == 'simple' and txt.startswith('开户账号：'):
            _append_value(para, (b.get('bank_account') or '').strip())
            continue
        if kind == 'simple' and txt.startswith('开户名称：'):
            _append_value(para, (b.get('bank_name') or b_name).strip())
            continue

        # 签署页 甲方/乙方 一行（主合同和附件2都有；模板里可能写成「乙方 ：」带空格）
        if txt.startswith('甲方：'):
            mb = re.search(r'乙方\s*：', txt)
            if mb:
                gap = txt[len('甲方：'):mb.start()]
                if '\t' in gap:
                    # 简易版用制表符对齐：插入名字后保留制表符，乙方仍会停在原来的制表位
                    new_gap = gap
                else:
                    # 框架合同是一长串空格：按名字宽度缩短，避免把乙方顶到下一行
                    new_gap = ' ' * max(len(gap) - _disp_width(a_name), 2)
                set_text(para, '甲方：%s%s乙方：%s' % (a_name, new_gap, b_name))
                continue

        # 附件1 反商业贿赂抬头
        if txt.strip() in ('甲  方：', '甲方：'):
            _set_labeled(para, '甲  方：' if '甲  方：' in txt else '甲方：', a_name)
            continue
        if txt.strip() in ('乙  方：', '乙方：'):
            _set_labeled(para, '乙  方：' if '乙  方：' in txt else '乙方：', b_name)
            continue

        # 附件2 / 简易版抬头
        if txt.startswith('购货单位（甲方）：'):
            _set_labeled(para, '购货单位（甲方）：', a_name)
            if kind == 'simple':
                simple_party = a
            continue
        if txt.startswith('供货单位（乙方）：'):
            _set_labeled(para, '供货单位（乙方）：', b_name)
            if kind == 'simple':
                simple_party = b
            continue

        # 单次简易版：紧跟抬头后面的联系人/电话/邮箱/地址
        if kind == 'simple' and simple_party is not None and txt.startswith(
                ('联系人：', '联系电话：', '联系邮箱：', '联系地址：')):
            _fill_simple_contact(para, simple_party)
            continue

        # 附件2 引用主合同签订日期（兼容 【】 和 【 】 两种写法）
        if '签订了《购销框架合同》' in txt and '【' in txt:
            fill_brackets(para, [y, m, d])
            rep(para, '%s 日' % d, '%s日' % d)     # 集采模板原文「【】 日」多一个空格
            continue

        # 单次简易版结算方式
        if kind == 'simple' and txt.startswith('结算方式：'):
            _fill_simple_settlement(para, t)
            continue

        # 集采模板：附件2 结算方式（税率/票种/开票天数直接写在句子里，没有【】占位符）
        if kind == 'batch' and re.match(r'^\s*结算方式\s*[:：]', txt):
            _fill_batch_settlement(para, t)
            continue

        # 旧批采模板 / 代发模板的结算条款
        if txt.startswith('1、结算方式：') or txt.startswith('1、结算方式'):
            if kind == 'batch':
                rep(para, '【3】个工作日', '【%s】个工作日' % t['invoice_days'])
                rep(para, '【 %】', '【%s】' % t['tax_rate'])
                rep(para, '【 】个工作日内', '【%s】个工作日内' % t['pay_days'])
            else:
                rep(para, '【2】个工作日', '【%s】个工作日' % t['reconcile_days'])
                rep(para, '【3】个工作日', '【%s】个工作日' % t['invoice_days'])
                rep(para, '【 %】', '【%s】' % t['tax_rate'])
                rep(para, '【】个工作日内', '【%s】个工作日内' % t['pay_days'])
            continue

        # 一件代发：无效发货订单占比阈值（法律条款，历史合同无人填过，给默认值并暴露到页面）
        if '订单总数【 %】' in txt or '订单总数【%' in txt:
            rep(para, '【 %】', '【%s%%】' % t['invalid_order_pct'])
            rep(para, '【%】', '【%s%%】' % t['invalid_order_pct'])
            continue

        # 集采 / 简易版：交货时间填具体日期（签约日 + 交货周期）
        if kind in ('batch', 'simple') and '前向甲方提供上述产品' in txt and '【' in txt:
            dd = add_days(today, t['delivery_days'])
            fill_brackets(para, [dd.year, dd.month, dd.day])
            continue

        # 交货时间（旧批采模板 / 代发模板）
        if '个自然日内向甲方' in txt and ('【】' in txt or '【 】' in txt):
            fill_brackets(para, [t['delivery_days']])
            continue
        if '个自然日内向甲方及/或甲方客户' in txt and '【】' in txt:
            fill_brackets(para, [t['delivery_days']])
            continue

        # 集采 / 简易版：交货地址（集采模板预填了花都仓，页面填了才覆盖；简易版本身是空的）
        if kind in ('batch', 'simple') and txt.startswith('交货地址：'):
            _set_labeled(para, '交货地址：', (p.get('terms') or {}).get('delivery_addr', '').strip())
            continue

        # 交货地址（旧批采模板留空的那行）
        if txt.startswith('3、交货地址：') or txt.startswith('4、交货地址：'):
            addr = (p.get('terms') or {}).get('delivery_addr', '').strip()
            if addr:
                _append_value(para, addr)
            continue

        # 签署日期行（两处签署日期都要填）
        if txt.startswith('签署日期') and '年' in txt:
            raw = para.text
            new = re.sub(r'(签署日期[：:])[\s\u00a0]*年[\s\u00a0]*月[\s\u00a0]*日',
                         lambda mm: '%s%s年%s月%s日' % (mm.group(1), y, m, d), raw)
            if new != raw:
                set_text(para, new)
            continue

    # ---- 2) 表格 ----
    for tb in doc.tables:
        for row in tb.rows:
            cells = row.cells
            if len(cells) < 2:
                continue
            for ci, cell in enumerate(cells[:2]):
                src = a if ci == 0 else b
                _fill_cell(cell, src)
            # 附件2 表头：单价（人民币：元）（含税运专票【】价）
            # 历史合同的实际写法：含税运专票13%价 / 含税运普票1%价
            # 集采模板的「含13%增值税专票+运费」也按页面税率/票种同步
            for cell in cells:
                _fill_price_header(cell, t)
                _fill_tax_note(cell, t)
                # 订单总金额：批采填附件2的「xxx元 / ¥xx元」；简易版填总费用和大写
                if amount:
                    for para in cell.paragraphs:
                        if kind == 'batch':
                            rep(para, '¥xx元', '¥%s元' % amount)
                        elif kind == 'simple':
                            rep(para, '本次产品订购的总费用为【】元',
                                '本次产品订购的总费用为%s元' % amount)
                            if amount_cn:
                                rep(para, '（大写：）', '（大写：%s）' % amount_cn)

    # ---- 3) 保存 ----
    os.makedirs(OUT_DIR, exist_ok=True)
    # 加毫秒 + 类型，避免同一秒内生成多份时互相覆盖
    stamp = datetime.now().strftime('%m%d%H%M%S') + '%03d' % (datetime.now().microsecond // 1000)
    prefix = {
        'batch': '购销框架合同_批采',
        'dropship': '购销框架合同_代发',
        'simple': '产品订购协议_单次',
    }.get(kind, '购销框架合同')
    if (b_name or '').strip():
        stem = '%s_%s_%s' % (prefix, safe_name(b_name, 20), stamp)
    else:
        stem = '%s_%s' % (prefix, stamp)
    fname = stem + '.docx'
    path = os.path.join(OUT_DIR, fname)
    clear_yellow(doc)
    doc.save(path)

    # 主动清点还剩哪些空没有填（例如订购清单金额本就应该每次下单时再填）
    todo = collect_todo(doc)
    return {'ok': True, 'name': fname, 'path': path,
            'url': urllib.parse.quote('/_生成合同/' + fname, safe='/'),
            'todo': todo}


CELL_MAP = {
    '购货单位（甲方）：': 'name',
    '供货单位（乙方）：': 'name',
    '统一社会信用代码：': 'credit_code',
    '联系人：': 'contact',
    '联系电话：': 'tel',
    '联系邮箱：': 'email',
    '联系地址：': 'addr',
}


def _fill_batch_settlement(para, t):
    """集采模板附件2的结算句：

    「…甲方支付全部款项后7个工作日内向甲方开具等额合法有效的13%增值税专用发票。」
    句子里的 13% / 专票 / 7个工作日 是写死的，需要跟着页面上的
    开票税率、发票类型、开票期限走，否则页面选了普票 1%，合同里还是 13% 专票。
    """
    amount = clean_amount(t.get('order_amount'))
    if amount:
        set_text(para, ' 结算方式:' + _pay_clause(t, amount))
        return
    rate = str(t.get('tax_rate') or '').strip()
    inv = str(t.get('invoice_type') or '专票').strip()
    days = str(t.get('invoice_days') or '').strip()

    if rate:
        if not rate.endswith('%'):
            rate += '%'
        if rate != '13%':
            rep_re(para, r'\d+(?:\.\d+)?%', rate)

    if inv == '普票':
        # 整词优先；跨 run 时退化为只换「专用」两个字
        if not rep(para, '专用发票', '普通发票'):
            rep(para, '专用', '普通')
        rep(para, '专票', '普票')

    if days.isdigit() and days != '7':
        rep(para, '7个工作日', '%s个工作日' % days)


def _fill_tax_note(cell, t):
    """表格备注里的「含13%增值税专票+运费」跟着税率/票种走"""
    rate = str(t.get('tax_rate') or '').strip()
    inv = str(t.get('invoice_type') or '专票').strip()
    if rate and not rate.endswith('%'):
        rate += '%'
    for para in cell.paragraphs:
        txt = para.text
        if '增值税' not in txt or '票' not in txt:
            continue
        if rate and rate != '13%':
            rep_re(para, r'\d+(?:\.\d+)?%', rate)
        if inv == '普票':
            rep(para, '专票', '普票')
            rep(para, '专用发票', '普通发票')


def _fill_price_header(cell, t):
    """填「单价（人民币：元）（含税运专票【】价）」这一格。

    依据 421 份已签合同：空格里填的是税率，且票种可为 专票/普票。
    结果形如：含税运专票13%价
    """
    rate = str(t.get('tax_rate') or '').strip()
    inv = str(t.get('invoice_type') or '专票').strip()
    if not rate.endswith('%'):
        rate = rate + '%'
    for para in cell.paragraphs:
        txt = para.text
        if '含税运' not in txt or '【' not in txt:
            continue
        # 票种
        if inv and inv not in txt:
            rep(para, '专票', inv)
            txt = para.text
        rep(para, '【】', rate)
        rep(para, '【 】', rate)


def _fill_cell(cell, src):
    for para in cell.paragraphs:
        txt = para.text.strip()
        if not txt:
            continue
        # 主合同签署表
        if txt.startswith('甲方（盖章）：') or txt.startswith('乙方（盖章）：'):
            _set_labeled(para, txt[:txt.index('：') + 1], (src.get('name') or '').strip())
            continue
        if txt.startswith('法定代表人（签字/盖章）：'):
            _set_labeled(para, '法定代表人（签字/盖章）：', (src.get('legal') or '').strip())
            continue
        if txt.startswith('法定代表人：'):
            _set_labeled(para, '法定代表人：', (src.get('legal') or '').strip())
            continue
        # 附件2 甲乙双方信息表（集采模板里甲方是预填的，用 _set_labeled 才不会重复）
        for label, key in CELL_MAP.items():
            if txt.startswith(label):
                _set_labeled(para, label, (src.get(key) or '').strip())
                break


# ---------------- 供应商信息收集表 ----------------
INFO_ITEMS = [
    ('公司全称', '须与营业执照完全一致', True),
    ('统一社会信用代码', '', True),
    ('法定代表人', '', False),
    ('联系人', '', True),
    ('联系电话', '', True),
    ('联系邮箱', '', True),
    ('联系地址', '须能收寄快递', True),
    ('开户名称', '对公账户名，须与公司全称一致', True),
    ('对公账号', '', True),
    ('开户行', '请精确到支行，如：中国建设银行股份有限公司汕头东里支行', True),
    ('开票税率', '如 13% / 6% / 3% / 1%', True),
    ('发票类型', '增值税专用发票 / 增值税普通发票', True),
    ('常规交货周期', '下单后几个自然日内发货', True),
    ('质保期', '如 1 年', False),
    ('备注', '', False),
]


def make_info_sheet(p):
    a = p.get('party_a', {})
    b = p.get('party_b', {})
    doc = Document()

    # 中文字体
    st = doc.styles['Normal']
    st.font.name = '微软雅黑'
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')

    title = doc.add_paragraph()
    tr = title.add_run('供应商合作信息收集表')
    tr.bold = True
    tr.font.size = Pt(20)
    title.alignment = 1

    tip = doc.add_paragraph()
    tr2 = tip.add_run(
        '您好！为推进合同签订，烦请填写下表信息并发回。第 1、2、8、9、10 项须与营业执照/开户许可证完全一致，'
        '否则会影响付款与开票。')
    tr2.font.size = Pt(10)
    tr2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    meta = doc.add_paragraph()
    meta.add_run('采购方：%s    ' % (a.get('name') or '广州兴趣岛信息科技有限公司'))
    meta.add_run('拟合作方：%s    ' % (b.get('name') or '（待填）'))
    meta.add_run('日期：%s' % datetime.now().strftime('%Y 年 %m 月 %d 日'))

    tb = doc.add_table(rows=1, cols=3)
    tb.style = 'Table Grid'
    hdr = tb.rows[0].cells
    for i, h in enumerate(['项目', '请填写', '说明']):
        hdr[i].text = h
        for para in hdr[i].paragraphs:
            for r in para.runs:
                r.bold = True

    for name, note, _req in INFO_ITEMS:
        row = tb.add_row().cells
        mark = '＊' if _req else ''
        row[0].text = (mark + name)
        row[1].text = (b.get(_map_key(name)) or '')
        row[2].text = note

    doc.add_paragraph()
    foot = doc.add_paragraph()
    fr = foot.add_run(
        '注：带 ＊ 的为必填项。账户如有变更请第一时间书面通知我方；因账户信息不准确造成的损失由贵司承担。')
    fr.font.size = Pt(9)
    fr.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime('%m%d%H%M%S')
    fname = '供应商信息收集表_%s_%s.docx' % (safe_name(b.get('name') or '新供应商', 16), stamp)
    path = os.path.join(OUT_DIR, fname)
    doc.save(path)
    url = urllib.parse.quote('/_生成合同/' + fname, safe='/')
    return {'ok': True, 'name': fname, 'path': path, 'url': url}


def _map_key(cn):
    return {
        '公司全称': 'name',
        '统一社会信用代码': 'credit_code',
        '法定代表人': 'legal',
        '联系人': 'contact',
        '联系电话': 'tel',
        '联系邮箱': 'email',
        '联系地址': 'addr',
        '开户名称': 'bank_name',
        '对公账号': 'bank_account',
        '开户行': 'bank_open',
    }.get(cn, '')


if __name__ == '__main__':
    _utf8_console()
    demo = {
        'contract_type': 'batch',
        'party_a': {'name': '广州兴趣岛信息科技有限公司', 'contact': '李明',
                    'tel': '13800000000', 'email': 'demo@example.com',
                    'addr': '广州市天河区某某路1号'},
        'party_b': {'name': '测试科技有限公司', 'credit_code': '91440000XXXXXXXXXX',
                    'contact': '张三', 'tel': '13900000000', 'email': 'test@test.com',
                    'addr': '深圳市南山区某大厦', 'legal': '李四',
                    'bank_name': '测试科技有限公司', 'bank_account': '1234567890123456',
                    'bank_open': '招商银行深圳某某支行'},
        'sign': {'date': '2026-10-15', 'years': '1', 'place': '广州市天河区'},
        'terms': {'tax_rate': '13%', 'invoice_days': '15', 'pay_days': '15',
                  'delivery_days': '10', 'delivery_addr': '广州市天河区沐陂西街8号大院A08'},
    }
    print(make_contract(demo))
    print(make_info_sheet(demo))
