# -*- coding: utf-8 -*-
"""产品搜索回归：SQL 下推后的结果必须与原来的"全量过滤 + 排序"完全一致。

依赖 data/purchase.db（只读）。没有数据库时自动跳过。
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _loader


class SearchEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = _loader.store()
        cls.products, cls.suppliers = cls.store.get_catalog()
        if not cls.products:
            raise unittest.SkipTest('没有产品数据')

    def legacy_search(self, raw, supplier_code=None, limit=20):
        """重构前的算法：整目录过滤 + 排序（作为基准）"""
        q = self.store._norm_text(raw)
        if not q:
            return []
        sup_keys = set()
        if supplier_code:
            sup = next((s for s in self.suppliers if s['id'] == supplier_code), None)
            if sup:
                sup_keys = set(sup['产品keys'])
        hits = [p for p in self.products if self.store._product_hit(p, q, len(raw))]
        hits.sort(key=lambda p: (
            0 if p['id'] in sup_keys else 1,
            0 if p.get('图片') else 1,
            -int(p.get('下单次数') or 0),
        ))
        return [p['id'] for p in hits[:limit]]

    def query_pool(self):
        queries = set()
        for p in self.products[:200]:
            name = p['产品名称']
            for size in (1, 2, 3, 4):
                if len(name) >= size:
                    queries.add(name[:size])
            for alias in (p.get('别名') or [])[:1]:
                if alias:
                    queries.add(alias[:3])
            spec = p.get('规格') or ''
            if len(spec) >= 4:
                queries.add(spec[:4])
        queries.update(['汉印', 'U盘', '麦克风', '%', '_', '\\', '不存在的产品xyz'])
        return sorted(queries)

    def test_same_results_for_many_queries(self):
        queries = self.query_pool()
        self.assertGreater(len(queries), 50, '查询样本太少')
        for raw in queries:
            with self.subTest(query=raw):
                expected = self.legacy_search(raw, limit=1000)
                actual = [p['id'] for p in self.store.search_products(raw, None, 1000)]
                self.assertEqual(actual, expected)

    def test_supplier_priority(self):
        supplier = next((s for s in self.suppliers if len(s['产品keys']) > 3), None)
        if not supplier:
            self.skipTest('没有合适的供应商')
        raw = '卡'
        expected = self.legacy_search(raw, supplier['id'], limit=1000)
        actual = [p['id'] for p in self.store.search_products(raw, supplier['id'], 1000)]
        self.assertEqual(actual, expected)

    def test_limit_and_empty(self):
        self.assertEqual(len(self.store.search_products('', None, 20)), 0)
        self.assertEqual(len(self.store.search_products('   ', None, 20)), 0)
        self.assertLessEqual(len(self.store.search_products('a', None, 5)), 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
