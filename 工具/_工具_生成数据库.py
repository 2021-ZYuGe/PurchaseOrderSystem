# -*- coding: utf-8 -*-
"""
采购下单系统 —— 一键从合同数据生成属于自己的系统

同事用法：
  1. 把从财务申请导出的合同文件夹放到任意位置（含 .docx 合同的文件夹）
  2. 双击"工具\\一键生成我的系统.bat"
  3. 按提示输入合同文件夹路径 → 自动生成系统

生成内容：
  data/purchase.db  SQLite 正式数据库（产品库 + 供应商库 + 主合同信息）
  web/data.js      由 SQLite 生成的网页兼容缓存
  web/图片/         所有产品图片
  Excel 版数据       （可选）
"""
import os
import re
import sys
import json
import zipfile
import hashlib
from pathlib import Path
from collections import defaultdict

try:
    from docx import Document
    from docx.oxml.ns import qn
except ImportError:
    print("[错误] 缺少 python-docx 库。请先运行：pip install python-docx")
    sys.exit(1)


# ============ 工具函数 ============
CLEAN_RE = re.compile(r"[\n\r\t]+")
DIRTY_KEYWORDS = [
    "总费用为", "合计", "上述产品", "本产品订单", "甲乙双方", "签订", "清单",
    "合同", "条款", "结算方式", "预付", "尾款", "发票", "验收", "违约责任",
    "购货单位", "供货单位", "联系人", "交货地址", "签署日期", "盖章",
    "产品订购清单", "购销框架", "购买需求", "备用量", "退换",
]
HEADER_WORDS = {"商品名称", "产品名称", "货物名称", "品名", "名称",
                "商品图片", "产品图片", "图片", "照片",
                "规格", "型号", "规格型号",
                "数量", "单价", "单价（含税）", "单个价格", "价格",
                "总金额", "金额", "总价", "小计", "合计",
                "备注", "序号"}


def is_dirty_name(s):
    """判断是否是被误抓的条款/合计文字"""
    if not s:
        return True
    s = s.strip()
    if len(s) > 60 or len(s) < 2:
        return True
    if s in HEADER_WORDS:
        return True
    # 合计行 / 纯金额行 / 含"元，"的长句
    s_np = s.replace(" ", "")
    if re.match(r"^合计", s_np):
        return True
    if "除前述费用外" in s_np or "无需支付" in s_np:
        return True
    if re.match(r"^[（(]?含税[）)]?$", s_np):
        return True
    # 超过 70% 是数字/符号，认为是金额行而非产品名
    if len(s_np) >= 4:
        numish = sum(1 for ch in s_np if ch.isdigit() or ch in "¥￥,，.。元+-%")
        if numish / len(s_np) > 0.5:
            return True
    for kw in DIRTY_KEYWORDS:
        if kw in s and len(s) > 12:
            return True
    return False


def clean_text(v):
    if v is None:
        return ""
    return CLEAN_RE.sub(" ", str(v)).strip()


def parse_money(s):
    """从文本中提取金额数字"""
    if not s:
        return None
    s = str(s).replace(",", "").replace("，", "").replace("￥", "").replace("¥", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v if v > 0 else None
    except ValueError:
        return None


CN_NUM = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
          "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
          "陆": 6, "柒": 7, "捌": 8, "玖": 9, "拾": 10}


def cn2int(s):
    """中文数字转整数（支持 2026 / 二〇二六 / 壹拾 等）"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    digits = [CN_NUM.get(ch) for ch in s]
    if None in digits:
        return None
    # 全部是数字字符，直接拼
    if all(d <= 9 for d in digits):
        return int("".join(str(d) for d in digits))
    # 含"十/拾"：如 十一 -> 11
    if 10 in digits:
        i = digits.index(10)
        head = digits[:i]
        tail = digits[i + 1:]
        h = int("".join(str(d) for d in head)) if head else 1
        t = int("".join(str(d) for d in tail)) if tail else 0
        return h * 10 + t
    return None


MAIN_DATE_RES = [
    re.compile(r"已于\s*【\s*([0-9〇零一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{2,6})\s*】\s*年"
               r"\s*【\s*([0-9〇零一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{1,3})\s*】\s*月"
               r"\s*【\s*([0-9〇零一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{1,3})\s*】\s*日"),
    re.compile(r"已于\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
]

# 落款签署日期：签署日期：2026年10月23日 / 签订日期: 2026.10.23 都兼容
SIGN_DATE_RE = re.compile(
    r"(?:签署日期|签订日期)[^0-9]{0,6}(\d{4})\s*[年.\-/]\s*(\d{1,2})\s*[月.\-/]\s*(\d{1,2})"
)


def parse_main_contract_date(doc):
    """从文档里抓'甲乙双方已于【X】年【Y】月【Z】日签订'"""
    texts = []
    for p in doc.paragraphs:
        texts.append(p.text)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                texts.append(c.text)
    joined = "\n".join(texts)
    for rx in MAIN_DATE_RES:
        m = rx.search(joined)
        if m:
            y, mo, d = (cn2int(m.group(i)) for i in (1, 2, 3))
            if y and mo and d and 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def parse_sign_dates(doc):
    """抓落款处的「签署日期：2026年10月23日」。

    一份合同通常甲乙双方各写一处，日期可能相同也可能不同，
    这里全部保留，后续取最大值作为“最近签约”。
    """
    lines = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                lines.append(cell.text)
    out = []
    for line in lines:
        if not line or ("签署日期" not in line and "签订日期" not in line):
            continue
        for m in SIGN_DATE_RE.finditer(line):
            y, mo, d = (int(g) for g in m.groups())
            if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                out.append("%04d-%02d-%02d" % (y, mo, d))
    return out[:6]


# 合同期限：新版模板「本合同期限为1年，自2026年11月6日起至2027年11月5日止」
# 老版模板带方括号和空格「自 【2023】年 【11】 月【15】日起至【2024】年【11】月【14】日止」
TERM_DATE = r"[0-9〇零一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]{1,4}"
TERM_RE = re.compile(
    r"(?:本合同|本协议|合同|协议)(?:的)?(?:有效期限|有效期|期限)"
    r"[^。；\n]{0,40}?自\s*(%s)\s*年\s*(%s)\s*月\s*(%s)\s*日?\s*起"
    r"\s*至\s*(%s)\s*年\s*(%s)\s*月\s*(%s)\s*日?\s*止" % ((TERM_DATE,) * 6)
)
# 少数合同写成「有效期：2026年1月1日至2026年12月31日」，没有「自…起」
TERM_RANGE_RE = re.compile(
    r"(?:本合同|本协议|合同|协议)(?:的)?(?:有效期限|有效期|期限)"
    r"[^。；\n]{0,30}?(%s)\s*年\s*(%s)\s*月\s*(%s)\s*日?\s*(?:至|到|—|－|-|~|～)\s*"
    r"(%s)\s*年\s*(%s)\s*月\s*(%s)\s*日" % ((TERM_DATE,) * 6)
)


def _clean_term_text(text):
    """去掉方括号和所有空白，让「自 【2023】年 【11】 月」也能正则命中"""
    text = str(text or "")
    for ch in "【】〔〕[]":
        text = text.replace(ch, "")
    return re.sub(r"\s+", "", text)


def parse_contract_term(doc):
    """抓合同第十一条的「本合同期限为…自…起至…止」，返回 (起始日, 到期日)。

    解析不到就返回空字符串，绝不猜日期 —— 没写期限的老合同交给页面手工登记。
    """
    texts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                texts.append(cell.text)
    cleaned = [_clean_term_text(x) for x in texts if str(x or "").strip()]
    if not cleaned:
        return "", ""
    # 先逐段找（最准），再整篇拼一次（有的模板把这一条拆成了几个段落/表格单元格）
    for text in cleaned + ["".join(cleaned)]:
        for rx in (TERM_RE, TERM_RANGE_RE):
            for m in rx.finditer(text):
                parts = [cn2int(g) for g in m.groups()]
                if any(p is None for p in parts):
                    continue
                y1, mo1, d1, y2, mo2, d2 = parts
                if not (2000 <= y1 <= 2100 and 2000 <= y2 <= 2100):
                    continue
                if not (1 <= mo1 <= 12 and 1 <= mo2 <= 12):
                    continue
                if not (1 <= d1 <= 31 and 1 <= d2 <= 31):
                    continue
                start = "%04d-%02d-%02d" % (y1, mo1, d1)
                end = "%04d-%02d-%02d" % (y2, mo2, d2)
                if end < start:
                    continue
                return start, end
    return "", ""


def contract_no_of(path):
    """从文件名或所在文件夹名取易快报单号，如 S26013838"""
    for text in (Path(path).name, Path(path).parent.name):
        m = re.match(r"(S\d{8})", str(text), re.I)
        if m:
            return m.group(1).upper()
    return ""


def supplier_from_tables(doc):
    """部分合同的乙方信息写在表格里：供货单位（乙方）：| 公司名"""
    for table in doc.tables:
        for row in table.rows:
            cells = row.cells
            for i, cell in enumerate(cells):
                text = clean_text(cell.text)
                if "供货单位" not in text:
                    continue
                m = re.search(r"[：:]\s*(\S[^\n]{1,38})", text)
                if m and clean_text(m.group(1)):
                    return re.split(r"[\s　]", clean_text(m.group(1)))[0]
                if i + 1 < len(cells):
                    value = clean_text(cells[i + 1].text)
                    if value and "：" not in value and ":" not in value:
                        return re.split(r"[\s　]", value)[0]
    return ""


def accept_revisions(doc):
    """接受文档里的全部修订痕迹（w:ins / w:del），让正文和表格读到“最终稿”文字。

    Word 里另存或转发过的合同常带着未接受的修订：产品名、规格、单价等整段文字
    被包在 <w:ins> 里。python-docx 的 paragraph.text / cell.text 只取段落直属的
    run，会把 <w:ins> 里的 run 漏掉，于是表格看起来是空的、一份产品都提不出来。
    这里把 inserted 内容提升到原位、把 deleted 内容删掉（等价于 Word 里点
    “接受所有修订”），后续所有解析都基于最终稿。
    """
    body = doc.element.body
    for tag in ("w:del", "w:moveFrom"):
        for el in list(body.iter(qn(tag))):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    for tag in ("w:ins", "w:moveTo"):
        # 修订可以嵌套，多轮直到清空
        for _ in range(8):
            items = list(body.iter(qn(tag)))
            if not items:
                break
            for el in items:
                parent = el.getparent()
                if parent is None:
                    continue
                idx = parent.index(el)
                for child in list(el):
                    el.remove(child)
                    parent.insert(idx, child)
                    idx += 1
                parent.remove(el)


def has_product_table(doc):
    """是否含真正有数据的产品表格（用来区分空白模板/非采购合同）"""
    for table in doc.tables:
        if len(table.rows) < 2:
            continue
        header = [clean_text(c.text) for c in table.rows[0].cells]
        ci_name = find_col(header, ["商品名称", "产品名称", "货物名称", "品名"])
        if ci_name < 0:
            ci_name = find_col(header, ["名称"])
        if ci_name < 0:
            continue
        for row in table.rows[1:]:
            if ci_name < len(row.cells) and clean_text(row.cells[ci_name].text):
                return True
    return False


def find_col(header_row, keywords):
    """在表头行里定位列索引"""
    for i, c in enumerate(header_row):
        t = clean_text(c).replace(" ", "")
        for kw in keywords:
            if kw in t:
                return i
    return -1


def extract_cell_images(doc, cell):
    """取单元格里的图片二进制"""
    out = []
    try:
        from docx.oxml.ns import qn
        blips = cell._tc.findall(".//" + qn("a:blip"))
        for blip in blips:
            rid = blip.get(qn("r:embed"))
            if not rid:
                continue
            part = doc.part.related_parts.get(rid)
            if part is not None:
                out.append((part.blob, part.partname.ext if hasattr(part.partname, "ext") else "png"))
    except Exception:
        pass
    return out


# ============ 主流程 ============
def walk_docx(root):
    files = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            if n.lower().endswith(".docx") and not n.startswith("~$"):
                files.append(os.path.join(dirpath, n))
    return files


def pause(msg="\n按回车退出…"):
    """交互式等待；在无终端/管道环境下自动跳过"""
    try:
        input(msg)
    except EOFError:
        pass


def main():
    print("=" * 56)
    print("        采购下单系统  数据生成工具")
    print("=" * 56)
    print()

    # 支持两种用法：
    #   1) 直接传路径： python _工具_生成数据库.py "D:\我的合同"
    #   2) 双击运行后交互输入
    if len(sys.argv) > 1 and sys.argv[1].strip():
        root = sys.argv[1].strip().strip('"').strip("'")
        print(f"合同文件夹：{root}")
    else:
        print("请把【从财务申请导出的合同文件夹】路径粘贴进来。")
        print("（在文件夹地址栏复制路径即可）")
        print()
        try:
            root = input("合同文件夹路径：").strip().strip('"').strip("'")
        except EOFError:
            root = ""

    if not root or not os.path.isdir(root):
        print(f"\n[错误] 找不到文件夹：{root}")
        pause()
        return

    docs = walk_docx(root)

    # 可选：环境变量 CAIGOU_ONLY 指向一个文件清单，只处理清单里列出的合同
    # （增量合并用，不影响正常全量用法）
    _only = os.environ.get("CAIGOU_ONLY")
    if _only and os.path.isfile(_only):
        want = set()
        for line in open(_only, encoding="utf-8"):
            line = line.strip()
            if line:
                want.add(os.path.abspath(line))
        docs = [d for d in docs if os.path.abspath(d) in want]
    elif "_增量批次_" in Path(__file__).resolve().parent.name:
        # 安全阀：被“合并新合同”复制到增量目录，却没拿到本批清单，
        # 说明两个脚本版本对不上。此时继续会变成全量重导，宁可直接停下。
        print("\n[错误] 这是增量批次，但没有收到待处理合同清单。")
        print("      多半是 工具\\合并新合同.py 与本脚本版本不一致。")
        print("      已中止，原有数据未做任何改动；请把两个脚本一起更新后重试。")
        pause()
        return

    print(f"\n找到 {len(docs)} 份 docx 合同，开始解析…\n")
    if not docs:
        print("[错误] 该文件夹里没有 .docx 文件。")
        pause()
        return

    here = Path(__file__).resolve().parent
    # 正常运行时脚本在 工具/ 下，项目根目录是上一级；
    # “合并新合同”会把脚本复制到独立的 工具/_增量批次_*/ 里运行，按当前目录输出。
    if not (here / "web").exists():
        here = here.parent
    img_dir = here / "web" / "图片"
    # 图片只新增或按内容哈希覆盖，绝不在解析前清空；失败/回滚时旧图片仍可用。
    img_dir.mkdir(parents=True, exist_ok=True)

    products = defaultdict(lambda: {
        "名称": "", "规格": "", "价格": [], "次数": 0,
        "图片": "", "备选": [], "供应商": set()
    })
    suppliers = defaultdict(lambda: {"名称": "", "电话": "", "产品": set(), "合同日期": "", "合同数": 0})

    img_hashes = {}
    ok = fail = 0
    skipped = []
    nosup = []
    failed_names = []
    results = []
    main_dates = []
    contract_records = []

    for idx, path in enumerate(docs, 1):
        if idx % 50 == 0:
            print(f"  已处理 {idx}/{len(docs)} …")
        try:
            doc = Document(path)
        except Exception as e:
            fail += 1
            failed_names.append(Path(path).name)
            results.append({
                "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                "结果": "失败", "原因": "无法打开：%s" % e,
                "供应商": "", "正文日期": "",
            })
            continue
        # 先接受修订，否则表格里被修订包住的文字读不到（整批会被误判为“没有产品”）
        try:
            accept_revisions(doc)
        except Exception:
            pass

        # 供应商名：优先从"供货单位（乙方）"抓
        sup_name = ""
        all_text = "\n".join(p.text for p in doc.paragraphs)
        m = re.search(r"供货单位[（(]?乙方[）)]?\s*[:：]\s*([^\n]{2,40})", all_text)
        if m:
            sup_name = re.split(r"[\s　]", clean_text(m.group(1)))[0]
        if not sup_name:
            sup_name = supplier_from_tables(doc)
        if not sup_name:
            stem = clean_text(Path(path).stem)
            stem = re.sub(r"^(合同|附件|订购清单)[-_]?", "", stem)
            # 文件名里带单号或“合同/清单”的，不是供应商名；这类多半是空白模板或非采购合同
            if re.match(r"^S\d{8}", stem) or "合同" in stem or "清单" in stem:
                if not has_product_table(doc):
                    skipped.append(Path(path).name)
                    results.append({
                        "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                        "结果": "跳过", "原因": "空白模板/非采购合同",
                        "供应商": "", "正文日期": "",
                    })
                    continue
                # 有产品表但没有乙方信息：无法归属供应商，跳过并单独列出，不阻断整批
                nosup.append(Path(path).name)
                results.append({
                    "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                    "结果": "跳过", "原因": "缺供应商信息（有产品表）",
                    "供应商": "", "正文日期": "",
                })
                continue
            sup_name = stem[:30]
        if is_dirty_name(sup_name):
            # 空白模板、委托设计等非采购合同：没有乙方也没有产品表，跳过而不是判失败
            if not has_product_table(doc):
                skipped.append(Path(path).name)
                results.append({
                    "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                    "结果": "跳过", "原因": "空白模板/非采购合同",
                    "供应商": "", "正文日期": "",
                })
                continue
            fail += 1
            failed_names.append(Path(path).name)
            results.append({
                "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                "结果": "失败", "原因": "供应商名异常：%s" % sup_name,
                "供应商": "", "正文日期": "",
            })
            continue

        sup = suppliers[sup_name]
        sup["名称"] = sup_name
        sup["合同数"] += 1

        # 电话
        m = re.search(r"(1[3-9]\d{9})", all_text)
        if m and not sup["电话"]:
            sup["电话"] = m.group(1)

        # 主合同日期
        d = parse_main_contract_date(doc)
        if d:
            main_dates.append(d)
            if d > sup["合同日期"]:
                sup["合同日期"] = d

        # 合同级台账：增量合并时写回 SQLite，保证“最近签约”能取到落款日期
        term_start, term_end = parse_contract_term(doc)
        contract_records.append({
            "合同号": contract_no_of(path),
            "文件名": Path(path).name,
            "供应商": sup_name,
            "主合同日期": d or "",
            "签署日期": parse_sign_dates(doc),
            "合同起始": term_start,
            "合同截止": term_end,
        })

        # 表格提取
        got = 0            # 本份合同真正读到的产品行数
        for t in doc.tables:
            if len(t.rows) < 2:
                continue
            hdr = [clean_text(c.text) for c in t.rows[0].cells]
            ci_name = find_col(hdr, ["商品名称", "产品名称", "货物名称", "品名"])
            if ci_name < 0:
                ci_name = find_col(hdr, ["名称"])
            if ci_name < 0:
                continue
            ci_img = find_col(hdr, ["图片", "照片"])
            ci_spec = find_col(hdr, ["规格", "型号"])
            ci_price = find_col(hdr, ["单价", "单个价格", "价格"])
            ci_num = find_col(hdr, ["数量"])

            for row in t.rows[1:]:
                cells = row.cells
                if ci_name >= len(cells):
                    continue
                name = clean_text(cells[ci_name].text)
                if is_dirty_name(name):
                    continue

                spec = clean_text(cells[ci_spec].text) if 0 <= ci_spec < len(cells) else ""
                price = None
                if 0 <= ci_price < len(cells):
                    price = parse_money(cells[ci_price].text)

                imgs = []
                if 0 <= ci_img < len(cells):
                    imgs = extract_cell_images(doc, cells[ci_img])

                key = re.sub(r"\s+", "", name).lower()[:40]
                p = products[key]
                p["名称"] = name
                if spec and not p["规格"]:
                    p["规格"] = spec
                if price:
                    p["价格"].append(price)
                p["次数"] += 1
                p["供应商"].add(sup_name)
                sup["产品"].add(key)
                got += 1

                # 存图（按内容哈希去重）
                for blob, ext in imgs:
                    h = hashlib.md5(blob).hexdigest()[:10]
                    if h in img_hashes:
                        fn = img_hashes[h]
                    else:
                        safe = re.sub(r'[\\/:*?"<>|]', "_", name)[:40]
                        fn = f"{safe}_{h}.{ext}"
                        (img_dir / fn).write_bytes(blob)
                        img_hashes[h] = fn
                    if not p["图片"]:
                        p["图片"] = fn
                    elif fn != p["图片"] and fn not in p["备选"]:
                        p["备选"].append(fn)
        if got == 0:
            # 有乙方、也有表格的外形，但一行产品都没读到：多半是图片版清单、
            # 文字放在图形/文本框里，或排版特殊。按“跳过”记账，不让一份合同
            # 把整批拖成“没能解析出产品”。
            sup["合同数"] -= 1
            if sup["合同数"] <= 0 and not sup["产品"]:
                suppliers.pop(sup_name, None)
            if contract_records and contract_records[-1].get("文件名") == Path(path).name:
                contract_records.pop()
            skipped.append(Path(path).name)
            results.append({
                "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
                "结果": "跳过", "原因": "有表格但没读到产品行（可能是图片版清单）",
                "供应商": sup_name, "正文日期": d or "",
            })
            continue

        ok += 1
        results.append({
            "文件名": Path(path).name, "合同号": contract_no_of(path), "来源文件": str(path),
            "结果": "已导入", "原因": "",
            "供应商": sup_name, "正文日期": d or "",
            "产品数": got,
        })

    print(f"\n解析完成：成功 {ok} 份 / 跳过 {len(skipped) + len(nosup)} 份 / 失败 {fail} 份")
    if skipped:
        print("  跳过 %d 份（空白模板/非采购合同/图片版清单）：" % len(skipped)
              + "、".join(skipped[:5]) + (" 等" if len(skipped) > 5 else ""))
    if nosup:
        print("  缺供应商信息、未导入 %d 份：" % len(nosup) + "、".join(nosup[:5])
              + (" 等" if len(nosup) > 5 else ""))
    if failed_names:
        print("  解析失败：" + "、".join(failed_names[:5])
              + (" 等" if len(failed_names) > 5 else ""))
    print(f"提取产品 {len(products)} 个 / 供应商 {len(suppliers)} 家 / 图片 {len(img_hashes)} 张")

    # 增量批次输出逐份结果，供“合并新合同”生成未导入清单
    if os.environ.get("CAIGOU_ONLY"):
        try:
            (here / "web" / "_批次结果.json").write_text(
                json.dumps(results, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    if fail:
        # 部分成功不能覆盖正式库，也不能让增量批次把失败合同标记为已收录。
        raise RuntimeError("有 %d 份合同解析失败，正式数据未更新。请修复或移走失败合同后重试。" % fail)
    if not products:
        print("\n[错误] 没提取到任何产品，请确认合同里含标准的产品表格。")
        pause()
        return

    # ---------- 生成 data.js ----------
    def sort_price(ps):
        # 最近的价格优先（取最后一次出现的）
        return list(dict.fromkeys(reversed(ps)))[:5]

    P = []
    key2id = {}
    for i, (k, v) in enumerate(sorted(products.items(), key=lambda x: -x[1]["次数"]), 1):
        pid = f"P{i:04d}"
        key2id[k] = pid
        P.append({
            "id": pid,
            "产品名称": v["名称"],
            "规格": v["规格"],
            "历史单价": sort_price(v["价格"]),
            "下单次数": v["次数"],
            "图片": v["图片"],
            "备选图片": v["备选"],
            "别名": [],
        })

    S = []
    for i, (k, v) in enumerate(sorted(suppliers.items(), key=lambda x: -x[1]["合同数"]), 1):
        S.append({
            "id": f"S{i:04d}",
            "供应商名称": v["名称"],
            "电话": v["电话"],
            "主合同日期": v["合同日期"],
            "历史合同份数": v["合同数"],
            "产品keys": [key2id[pk] for pk in v["产品"] if pk in key2id],
        })

    script_dir = Path(__file__).resolve().parent
    if script_dir.name == "工具" and (script_dir / "sqlite_store.py").exists():
        # 正式运行：SQLite 是唯一主库，data.js 由数据库自动导出。
        import sqlite_store
        sqlite_store.replace_catalog(P, S)
    else:
        # “合并新合同”的隔离批次只生成临时 data.js，不接触正式数据库。
        body = "const PRODUCTS = " + json.dumps(P, ensure_ascii=False, separators=(",", ":")) + ";\n"
        body += "const SUPPLIERS = " + json.dumps(S, ensure_ascii=False, separators=(",", ":")) + ";\n"
        stamp = hashlib.md5(body.encode("utf-8")).hexdigest()[:12]
        js = "// 临时批次数据，请勿手改\n"
        js += "const DATA_STAMP = '%s';\n" % stamp
        js += body
        (here / "web" / "data.js").write_text(js, encoding="utf-8")
        # 批次合同台账（含落款签署日期），供“合并新合同”写回 SQLite
        (here / "web" / "_批次合同.json").write_text(
            json.dumps(contract_records, ensure_ascii=False), encoding="utf-8"
        )

    has_img = sum(1 for p in P if p["图片"])
    print(f"\n[完成] 产品库 {len(P)} 个（带图 {has_img}）/ 供应商库 {len(S)} 家")
    print(f"       主合同日期已识别 {len(S)} 家中 {sum(1 for s in S if s['主合同日期'])} 家")
    print(f"\n现在可以双击【启动网页版.bat】使用了。")
    pause()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        pause("\n出错了，按回车退出…")
        sys.exit(1)
