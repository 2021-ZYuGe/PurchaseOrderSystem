# -*- coding: utf-8 -*-
"""纯逻辑回归测试：金额大写、付款条款、日期推算、到期分档。

这里断言的是"重构前的实际行为"，用来保证搬家过程不改结果。
其中个别值本身可能有业务瑕疵（见注释），先锁定，等 P2 再单独修，
不要在这个阶段顺手改掉——否则就不是"行为不变"的重构了。

运行：
    python -m unittest discover -s tests -v
"""
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _loader


class AmountToCnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = _loader.contract_doc()

    def test_common_amounts(self):
        cases = {
            1: '壹元整',
            10.5: '壹拾元伍角',
            100: '壹佰元整',
            1000: '壹仟元整',
            10000: '壹万元整',
            12345.67: '壹万贰仟叁佰肆拾伍元陆角柒分',
            999.99: '玖佰玖拾玖元玖角玖分',
            1234567.89: '壹佰贰拾叁万肆仟伍佰陆拾柒元捌角玖分',
            100000000: '壹亿元整',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(self.gen.amount_to_cn(float(value)), expected)

    def test_zero_returns_empty(self):
        self.assertEqual(self.gen.amount_to_cn(0), '')

    def test_known_quirk_missing_zero(self):
        # 现状：元位为 0 且只有分位时，缺一个"零"（应为 壹佰万元零伍分）。
        # 这是历史行为，P1 不动；P2 修金额时一并处理。
        self.assertEqual(self.gen.amount_to_cn(1000000.05), '壹佰万元伍分')


class CleanAmountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = _loader.contract_doc()

    def test_clean(self):
        self.assertEqual(self.gen.clean_amount('1,234.50'), '1234.50')
        self.assertEqual(self.gen.clean_amount(' ￥12500 '), '12500')

    def test_rejects_dirty(self):
        for raw in ('abc', '0', '12.345'):
            with self.subTest(raw=raw):
                self.assertEqual(self.gen.clean_amount(raw), '')


class PayClauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = _loader.contract_doc()

    def test_full_payment(self):
        text = self.gen._pay_clause(
            {'pay_mode': 'full', 'tax_rate': '13%', 'invoice_type': '专票'}, 1234567.89)
        self.assertIn('本产品订单总金额为1,234,567.89元', text)
        self.assertIn('13%增值税专用发票', text)
        self.assertNotIn('预付款', text)

    def test_prepay_30(self):
        text = self.gen._pay_clause(
            {'pay_mode': 'p30', 'tax_rate': '6%', 'invoice_type': '普票'}, 100)
        self.assertIn('支付30%预付款，即30.00元', text)
        self.assertIn('剩余尾款70.00元', text)
        self.assertIn('6%增值税普通发票', text)

    def test_prepay_50_current_rounding(self):
        # 现状：1234567.89 的 50% 分别四舍五入后相加，会比总额少 0.01。
        # 这是浮点存储的已知问题（P2 改整数分），此处锁定当前输出。
        text = self.gen._pay_clause(
            {'pay_mode': 'p50', 'tax_rate': '13%', 'invoice_type': '专票'}, 1234567.89)
        self.assertIn('即617,283.94元', text)
        self.assertIn('剩余尾款617,283.94元', text)


class DateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = _loader.contract_doc()

    def test_date_parts(self):
        self.assertEqual(self.gen.date_parts('2026-11-13'), (2026, 11, 13))

    def test_end_date(self):
        self.assertEqual(self.gen.end_date('2026-11-13', 1).strftime('%Y-%m-%d'), '2027-11-12')
        self.assertEqual(self.gen.end_date('2026-11-13', '2').strftime('%Y-%m-%d'), '2028-11-12')

    def test_add_days(self):
        self.assertEqual(self.gen.add_days('2026-11-13', 10).strftime('%Y-%m-%d'), '2026-11-23')

    def test_templates_exist(self):
        for kind in ('batch', 'dropship', 'simple'):
            with self.subTest(kind=kind):
                path = self.gen.ensure_tpl(kind)
                self.assertTrue(Path(path).is_file(), path)


class StorePureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = _loader.store()

    def test_expiry_bucket(self):
        cases = {
            0: 'd3', 1: 'd3', 15: 'd30', 30: 'd30', 31: 'd90', 60: 'd90',
            90: 'd90', 91: 'd180', 180: 'd180', 365: 'ok', -1: 'expired',
        }
        for days, expected in cases.items():
            with self.subTest(days=days):
                self.assertEqual(self.store.expiry_bucket(days), expected)

    def test_contract_no(self):
        self.assertEqual(self.store.contract_no_of('S25013453_xxx.docx'), 'S25013453')
        self.assertEqual(self.store.contract_no_of('S26013532_兴趣岛x采购合同.docx'), 'S26013532')
        self.assertEqual(self.store.contract_no_of('合同-2026.docx'), '')
        self.assertEqual(self.store.contract_no_of('abc.docx'), '')

    def test_normalize_path(self):
        got = self.store.normalize_path('data/../data/purchase.db')
        self.assertTrue(got.endswith('data' + __import__('os').sep + 'purchase.db'))
        self.assertEqual(got, self.store.normalize_path(got))


class SchemaGuardTests(unittest.TestCase):
    """旧程序打开新版数据时必须拒绝启动，不能静默降级写坏结构"""

    def setUp(self):
        self.store = _loader.store()
        self.tmp = Path(tempfile.mkdtemp(prefix='schema_'))
        self.saved = (self.store.DB_PATH, self.store.DATA_DIR, self.store.BACKUP_DIR)
        db = self.tmp / 'purchase.db'
        conn = sqlite3.connect(str(db))
        conn.execute('CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        conn.execute("INSERT INTO schema_meta VALUES('schema_version', '99')")
        conn.commit()
        conn.close()
        self.store.DB_PATH = db
        self.store.DATA_DIR = self.tmp
        self.store.BACKUP_DIR = self.tmp / 'backups'

    def tearDown(self):
        self.store.DB_PATH, self.store.DATA_DIR, self.store.BACKUP_DIR = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rejects_newer_schema(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.store.ensure_database()
        self.assertIn('更新版本', str(ctx.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
