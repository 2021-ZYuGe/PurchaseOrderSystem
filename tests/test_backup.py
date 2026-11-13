# -*- coding: utf-8 -*-
"""备份策略：每天只备份一次、旧 daily 备份自动清理、手动备份不受影响。"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _loader

ROOT = _loader.ROOT
REAL_DB = ROOT / 'data' / 'purchase.db'


class BackupTests(unittest.TestCase):
    def setUp(self):
        if not REAL_DB.exists():
            self.skipTest('没有 data/purchase.db')
        self.store = _loader.store()
        from app.services import backup
        self.backup = backup
        self.tmp = Path(tempfile.mkdtemp(prefix='bak_'))
        (self.tmp / 'backups').mkdir()
        shutil.copy2(REAL_DB, self.tmp / 'purchase.db')
        self.saved = (self.store.DB_PATH, self.store.DATA_DIR, self.store.BACKUP_DIR)
        self.store.DB_PATH = self.tmp / 'purchase.db'
        self.store.DATA_DIR = self.tmp
        self.store.BACKUP_DIR = self.tmp / 'backups'

    def tearDown(self):
        self.store.DB_PATH, self.store.DATA_DIR, self.store.BACKUP_DIR = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def daily_files(self):
        return sorted((self.tmp / 'backups').glob('purchase_*_daily.db'))

    def test_daily_only_once(self):
        first = self.backup.daily_if_needed()
        self.assertTrue(first and Path(first).is_file())
        self.assertIsNone(self.backup.daily_if_needed(), '当天第二次不应再备份')
        self.assertEqual(len(self.daily_files()), 1)

    def test_prune_keeps_latest_seven(self):
        base = time.time() - 10000
        for i in range(10):
            path = self.tmp / 'backups' / ('purchase_2026010%d_000000_000000_daily.db' % i)
            path.write_bytes(b'x')
            os.utime(path, (base + i * 10, base + i * 10))
        removed = self.backup.prune_daily()
        self.assertEqual(len(removed), 3)
        self.assertEqual(len(self.daily_files()), 7)
        # 保留的应该是最新的 7 个
        names = [p.name for p in self.daily_files()]
        self.assertNotIn('purchase_20260100_000000_000000_daily.db', names)
        self.assertIn('purchase_20260109_000000_000000_daily.db', names)

    def test_manual_backup_not_pruned(self):
        kept = self.store.backup_database('manual')
        self.assertTrue(Path(kept).is_file())
        self.backup.prune_daily()
        self.assertTrue(Path(kept).exists(), '手动备份不能被 daily 清理掉')
        self.assertIn('name', self.backup.manual())
        self.assertGreater(len(self.backup.snapshot_bytes()), 1024)


if __name__ == '__main__':
    unittest.main(verbosity=2)
