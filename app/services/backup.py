# -*- coding: utf-8 -*-
"""备份策略：每天首次启动自动备份一次，只保留最近 7 份。

手工备份（升级前、恢复前）不受保留策略影响，不会被这里删掉。
"""
import time
from pathlib import Path

from app.infra import store
from app.infra.logging import log

KEEP_DAILY = 7
MARKER_NAME = '.last_daily_backup'


def _marker():
    return Path(store.DATA_DIR) / MARKER_NAME


def daily_if_needed():
    """当天还没备份过就备份一次；返回备份文件路径或 None"""
    if not Path(store.DB_PATH).exists():
        return None
    today = time.strftime('%Y%m%d')
    try:
        if _marker().read_text(encoding='utf-8').strip() == today:
            return None
    except OSError:
        pass
    path = store.backup_database('daily')
    removed = prune_daily()
    try:
        _marker().parent.mkdir(parents=True, exist_ok=True)
        _marker().write_text(today, encoding='utf-8')
    except OSError:
        pass
    if path:
        log('每日备份：%s%s' % (Path(path).name,
                              ('，清理旧备份 %d 份' % len(removed)) if removed else ''))
    return path


def prune_daily(keep=KEEP_DAILY):
    """只清理 *_daily.db，不碰升级前/恢复前的备份"""
    folder = Path(store.BACKUP_DIR)
    if not folder.is_dir():
        return []
    files = sorted(
        (p for p in folder.glob('purchase_*_daily.db') if p.is_file()),
        key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for old in files[keep:]:
        try:
            old.unlink()
            removed.append(old.name)
        except OSError:
            pass
    return removed


def list_backups(limit=20):
    folder = Path(store.BACKUP_DIR)
    if not folder.is_dir():
        return []
    files = sorted(
        (p for p in folder.glob('*.db') if p.is_file()),
        key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [{
        'name': p.name,
        'size': p.stat().st_size,
        'time': time.strftime('%Y-%m-%d %H:%M', time.localtime(p.stat().st_mtime)),
    } for p in files]


def manual(reason='manual'):
    """手动备份（系统状态面板的「立即备份」）"""
    if not Path(store.DB_PATH).exists():
        return {'name': ''}
    path = store.backup_database(reason)
    return {'name': Path(path).name if path else ''}


def snapshot_bytes():
    """导出一份一致的数据库快照（WAL 模式下不能直接读文件）"""
    import shutil
    import sqlite3
    import tempfile

    if not Path(store.DB_PATH).exists():
        return b''
    folder = Path(tempfile.mkdtemp(prefix='snapshot_'))
    target = folder / 'snapshot.db'
    try:
        with sqlite3.connect(str(store.DB_PATH)) as source, \
                sqlite3.connect(str(target)) as dest:
            source.backup(dest)
        return target.read_bytes()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
