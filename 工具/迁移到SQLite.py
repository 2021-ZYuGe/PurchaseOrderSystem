# -*- coding: utf-8 -*-
"""把现有 JSON / data.js 一次性迁入 SQLite；可重复运行且不会覆盖已有数据库。"""
import sys

import sqlite_store


def main():
    verify_only = "--verify" in sys.argv
    if not verify_only:
        path = sqlite_store.ensure_database()
        print("SQLite 数据库：%s" % path)
        print("页面已改为实时查库，无需生成网页缓存。")

    result = sqlite_store.verify_database()
    counts = sqlite_store.database_counts()
    print("\n数据库完整性：%s" % result["integrity"])
    print("外键错误：%d，失效产品关系：%d" %
          (result["foreign_key_errors"], result["invalid_relations"]))
    print("\n当前数据库记录：")
    labels = {
        "products": "现行产品",
        "suppliers": "现行供应商",
        "supplier_products": "供应商-产品关系",
        "supplier_profiles": "供应商档案",
        "contracts": "主合同记录",
        "contract_sign_dates": "合同签署日期",
        "supplier_main_contracts": "供应商主合同汇总",
        "historical_order_items": "历史合同产品行",
        "imported_contract_files": "已收录合同索引",
    }
    for key, label in labels.items():
        print("  %-24s %d" % (label, counts.get(key, 0)))
    print("\n原 JSON 文件未删除，仅作为历史备份；正式数据以 SQLite 为准。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("迁移或校验失败：%s" % exc)
        raise
