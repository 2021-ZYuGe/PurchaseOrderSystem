# -*- coding: utf-8 -*-
"""回填合同期限（合同第十一条「自…年…月…日起至…年…月…日止」）

把历史合同正文里的有效期读出来写进数据库，首页的到期预警马上就有数据，
不用把全部合同重新导入一遍。

- 可重复运行：只更新解析到期限的合同，解析不到的不动。
- 只读合同文件，不改任何 Word 文件。
- 加 --dry-run 只看统计，不写数据库。
- 合同目录不在默认位置时，用 --dir=路径 指定（可多个）。

用法：双击本文件；或 运行环境\\python.exe 工具\\回填合同期限.py
     运行环境\\python.exe 工具\\回填合同期限.py --dir="D:\\合同下载"
"""
import importlib.util
import os
import sys

import sqlite_store

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEN = os.path.join(HERE, "_工具_生成数据库.py")


def _ensure_console_font():
    """控制台若是点阵字体（不含中文字形），切换成新宋体，避免中文显示成菱形"""
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class CONSOLE_FONT_INFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("nFont", wintypes.DWORD),
                ("dwFontSize", COORD),
                ("FontFamily", wintypes.UINT),
                ("FontWeight", wintypes.UINT),
                ("FaceName", wintypes.WCHAR * 32),
            ]

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        info = CONSOLE_FONT_INFOEX()
        info.cbSize = ctypes.sizeof(info)
        if not kernel.GetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
            return
        if info.FaceName in ("新宋体", "宋体", "SimSun", "Microsoft YaHei Mono"):
            return
        for face in ("新宋体", "SimSun"):
            info.FaceName = face
            if info.dwFontSize.Y <= 0:
                info.dwFontSize.Y = 16
            if kernel.SetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
                return
    except Exception:
        pass


def pause(msg="\n按回车关闭…"):
    try:
        input(msg)
    except EOFError:
        pass


def load_parser():
    """复用 _工具_生成数据库.py 里的期限解析，避免两套正则漂移"""
    if not os.path.exists(GEN):
        raise RuntimeError("找不到解析器：%s" % GEN)
    spec = importlib.util.spec_from_file_location("contract_gen", GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extra_dirs(argv):
    """命令行里额外指定的合同目录：--dir=路径，或直接把文件夹拖进来"""
    out = []
    for arg in argv:
        value = ""
        if arg.startswith("--dir="):
            value = arg.split("=", 1)[1]
        elif os.path.isdir(arg):
            value = arg
        value = value.strip().strip('"').strip("'")
        if value and os.path.isdir(value):
            out.append(value)
    return out


def iter_docx(dirs):
    seen = set()
    for root in dirs:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, names in os.walk(root):
            # 跳过工具自己的临时批次目录，里面是同一批合同的副本
            dirnames[:] = [d for d in dirnames if not d.startswith("_")]
            for name in names:
                if not name.lower().endswith(".docx") or name.startswith("~$"):
                    continue
                path = os.path.join(dirpath, name)
                key = os.path.normcase(os.path.abspath(path))
                if key in seen:
                    continue
                seen.add(key)
                yield path


def main():
    dry_run = "--dry-run" in sys.argv
    print()
    print("=" * 58)
    print("        采购下单系统 · 回填合同期限")
    print("=" * 58)
    print()

    sqlite_store.ensure_database()
    parser = load_parser()
    try:
        import docx
    except Exception as e:
        print("缺少 python-docx，无法读取合同：%s" % e)
        pause()
        return

    with sqlite_store.session() as conn:
        contracts = [dict(r) for r in conn.execute(
            "SELECT id, contract_no, filename, supplier_name, contract_end_date FROM contracts"
        )]
    if not contracts:
        print("数据库里还没有合同台账，请先运行「更新数据源」。")
        pause()
        return

    by_no, by_name = {}, {}
    for row in contracts:
        no = (row["contract_no"] or "").strip().upper()
        if no:
            by_no.setdefault(no, []).append(row)
        by_name.setdefault((row["filename"] or "").strip(), []).append(row)

    dirs = sqlite_store._candidate_contract_dirs()
    for extra in extra_dirs(sys.argv[1:]):
        key = os.path.normcase(os.path.abspath(extra))
        if all(os.path.normcase(os.path.abspath(d)) != key for d in dirs):
            dirs.insert(0, extra)
    print("合同来源目录：")
    for d in dirs:
        print("  · %s" % d)
    print()

    scanned = 0
    hit = 0
    no_term = 0
    unreadable = 0
    unmatched = 0
    updates = {}
    suppliers = set()
    samples = []

    for path in iter_docx(dirs):
        scanned += 1
        no = sqlite_store.contract_no_of(path)
        name = os.path.basename(path)
        rows = by_no.get(no) if no else None
        if not rows:
            rows = by_name.get(name) or by_name.get(name.split("_", 1)[-1])
        if not rows:
            unmatched += 1
            continue
        try:
            doc = docx.Document(path)
        except Exception:
            unreadable += 1
            continue
        start, end = parser.parse_contract_term(doc)
        if not (start and end):
            no_term += 1
            continue
        hit += 1
        for row in rows:
            updates[row["id"]] = (start, end)
            suppliers.add((row["supplier_name"] or "").strip())
        if len(samples) < 8:
            samples.append((name[:40], start, end))

    print("扫描 .docx：%d 份" % scanned)
    print("解析到期限：%d 份" % hit)
    print("  对应台账：%d 条 / 供应商 %d 家" % (len(updates), len(suppliers)))
    print("没有期限条款：%d 份（早期模板只写“签订之日起生效”）" % no_term)
    if unmatched:
        print("库里找不到对应合同：%d 份" % unmatched)
    if unreadable:
        print("打不开（.doc 或损坏）：%d 份" % unreadable)
    print()

    if samples:
        print("识别示例：")
        for name, start, end in samples:
            print("  %s  %s → %s" % (name.ljust(42), start, end))
        print()

    if not updates:
        print("没有可回填的期限。")
        pause()
        return
    if dry_run:
        print("（--dry-run 只统计，数据库未改动）")
        pause()
        return

    print("正在写入数据库…")
    changed = sqlite_store.set_contract_terms(
        [(cid, start, end) for cid, (start, end) in updates.items()]
    )
    print("已更新 %d 条合同台账。" % changed)
    print("页面刷新即可看到，无需重建缓存。")
    print()
    print("打开首页就能看到合同到期预警；没有期限的老合同可在预警面板里手工登记。")
    pause()


if __name__ == "__main__":
    _ensure_console_font()
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="gbk", errors="replace")
            sys.stderr.reconfigure(encoding="gbk", errors="replace")
    except Exception:
        pass
    try:
        main()
    except Exception as exc:
        print("\n出错了：%s" % exc)
        pause()
