# -*- coding: utf-8 -*-
"""历史合同甲方回填。

默认只读预览；确认后加 --apply 写库（写前自动备份）。

用法：
    runtime\\python.exe tools\\backfill_party_a.py
    runtime\\python.exe tools\\backfill_party_a.py --apply
    runtime\\python.exe tools\\backfill_party_a.py --dir "D:\\合同下载"
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.domain import parser  # noqa: E402
from app.infra import store  # noqa: E402

DEFAULT_DIR = r"C:\Users\PC\Desktop\合同下载"
NO_RE = re.compile(r"(S\d{8})", re.I)


def collect_files(folder):
    """按单号建索引；同一单号有多份文件时取第一个。"""
    index = {}
    for path in Path(folder).rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (".docx", ".doc"):
            continue
        match = NO_RE.search(path.name)
        if match:
            index.setdefault(match.group(1).upper(), path)
    return index


def main():
    argp = argparse.ArgumentParser(description="历史合同甲方回填")
    argp.add_argument("--apply", action="store_true", help="写库；不加只预览")
    argp.add_argument("--dir", default=DEFAULT_DIR, help="合同目录")
    argp.add_argument("--db", default="", help=argparse.SUPPRESS)
    args = argp.parse_args()
    if args.db:
        store.DB_PATH = Path(args.db)

    folder = Path(args.dir)
    if not folder.is_dir():
        print("找不到合同目录：%s" % folder)
        return 2

    store.ensure_database()
    files = collect_files(folder)
    with store.session() as conn:
        rows = conn.execute(
            "SELECT id, contract_no, filename, party_a, party_a_source "
            "FROM contracts ORDER BY id").fetchall()

    result = []
    counts = Counter()
    for row in rows:
        path = files.get((row["contract_no"] or "").upper())
        if path is not None:
            counts["有文件"] += 1
        if (row["party_a"] or "").strip():
            counts["已回填"] += 1
            continue
        if path is None:
            counts["无文件"] += 1
            result.append((row["id"], row["contract_no"], row["filename"], "", ""))
            continue
        try:
            party = parser.party_a_from_path(path)
        except Exception as exc:
            counts["读取失败"] += 1
            print("读取失败：%s（%r）" % (Path(path).name, exc))
            result.append((row["id"], row["contract_no"], row["filename"], "", str(path)))
            continue
        if party:
            counts["识别成功"] += 1
        else:
            counts["未识别"] += 1
        result.append((row["id"], row["contract_no"], row["filename"], party, str(path)))

    total = len(rows)
    print("合同总数：%d" % total)
    print("按单号匹配到文件：%d" % counts["有文件"])
    for key in ("识别成功", "未识别", "无文件", "读取失败", "已回填"):
        if counts[key]:
            print("  %s：%d" % (key, counts[key]))
    print("甲方分布：")
    for name, count in Counter(item[3] for item in result if item[3]).most_common():
        print("  %d  %s" % (count, name))
    missing = [item for item in result if not item[3]]
    if missing:
        print("未识别/无文件样例（最多 15 份）：")
        for item in missing[:15]:
            print("  %s  %s" % (item[1] or "-", item[2]))

    if not args.apply:
        print("\n这是只读预览，数据库没有改动。确认后加 --apply 执行。")
        return 0

    updates = [item for item in result if item[3]]
    if not updates:
        print("\n没有可写入的甲方，数据库没有改动。")
        return 0
    store.backup_database("before_party_a_backfill")
    with store.session(write=True) as conn:
        for cid, _no, _filename, party, path in updates:
            conn.execute(
                "UPDATE contracts SET party_a=?, party_a_source='content', source_path=? "
                "WHERE id=?",
                (party, path, cid),
            )
    print("\n已写入 %d 份合同的甲方，备份在 data/backups。" % len(updates))
    return 0


if __name__ == "__main__":
    sys.exit(main())
