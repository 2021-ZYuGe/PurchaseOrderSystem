# -*- coding: utf-8 -*-
"""核对「最近签约」日期（只读，不改任何数据）。

用法：
    双击运行，输入供应商名称（可只输入几个字）；
    或命令行：python 核对最近签约.py 索爱

判断口径：
    取该供应商所有合同里，正文“甲乙双方已于…年…月…日签订了《购销框架合同》”
    这句日期的最大值；同一天再比落款日期、单号。文末落款不参与判断。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sqlite_store

# 控制台直接写 Unicode；只有被管道/文件捕获时才转 GBK
try:
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="gbk", errors="replace")
        sys.stderr.reconfigure(encoding="gbk", errors="replace")
except Exception:
    pass


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def pause(msg="\n按回车关闭…"):
    try:
        input(msg)
    except EOFError:
        pass


def main():
    kw = sys.argv[1].strip() if len(sys.argv) > 1 else ask("输入供应商名称（可只输入几个字）：").strip()
    if not kw:
        print("没有输入供应商名称，已退出。")
        return

    with sqlite_store.session() as conn:
        names = [
            row["name"] for row in conn.execute(
                "SELECT name FROM suppliers WHERE name LIKE ? ORDER BY contract_count DESC, name",
                ("%" + kw + "%",),
            )
        ]
    if not names:
        print("\n找不到匹配的供应商：%s" % kw)
        print("（试试只输入公司名里的两三个字，比如“索爱”）")
        return
    if len(names) > 1:
        print("\n匹配到 %d 家，请输入更完整的名称后重试：" % len(names))
        for n in names[:15]:
            print("  - " + n)
        return

    name = names[0]
    _, suppliers = sqlite_store.get_catalog()
    sup = next((x for x in suppliers if x["供应商名称"] == name), None)
    if sup is None:
        print("供应商表里找不到：%s" % name)
        return

    print()
    print("=" * 68)
    print("供应商：%s" % name)
    print("页面应显示：%s%s" % (
        sup["最近签约日期"] or "（无）",
        (" · " + sup["最近合同号"]) if sup["最近合同号"] else "",
    ))
    print("合同台账：%d 份" % (sup["合同记录数"] or 0))
    print("=" * 68)

    with sqlite_store.session() as conn:
        records = [dict(r) for r in conn.execute(
            """SELECT c.contract_no, c.main_contract_date,
                      (SELECT MAX(sign_date) FROM contract_sign_dates d
                        WHERE d.contract_id = c.id) AS sign_date,
                      c.filename
                 FROM contracts c
                WHERE c.supplier_name = ?
                ORDER BY c.main_contract_date DESC, sign_date DESC, c.contract_no DESC""",
            (name,),
        )]
    if not records:
        print("\n台账里没有这家供应商的合同记录，页面只能用产品库的旧计数兜底。")
        return

    best = None
    for r in records:
        if not r["main_contract_date"]:
            continue
        key = (r["main_contract_date"], r["sign_date"] or "", r["contract_no"] or "")
        if best is None or key > best[0]:
            best = (key, r)
    newest = max(records, key=lambda r: (r["sign_date"] or "", r["contract_no"] or ""))

    print("\n%-2s %-12s %-12s %-12s %s" % ("", "单号", "正文日期", "落款日期", "文件"))
    print("-" * 68)
    for r in records:
        mark = ""
        if best and r is best[1]:
            mark += "√"
        if r is newest:
            mark += "★"
        print("%-2s %-12s %-12s %-12s %s" % (
            mark or " ",
            r["contract_no"] or "—",
            r["main_contract_date"] or "—",
            r["sign_date"] or "—",
            (r["filename"] or "")[:34],
        ))
    print("-" * 68)
    print("√ = 页面取的那一份（正文日期最大）")
    print("★ = 落款最新的一份")
    if best and newest is not best[1]:
        print("\n注意：√ 和 ★ 不是同一份。系统是按正文日期取最大值，")
        print("      不是按“最新签的那份文件”取——这正是当前的口径。")
    print("\n到网页搜索这家供应商，弹框里的日期和单号应与上面“页面应显示”一致。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n出错了：%s" % e)
    pause()
