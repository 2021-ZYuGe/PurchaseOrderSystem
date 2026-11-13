# -*- coding: utf-8 -*-
"""系统状态：版本、数据位置、备份情况，供「系统状态」面板使用。

只读，不触发导入/扫描等重操作。
"""
import time
from pathlib import Path

import app.config as config
from app.infra import store


def _fmt_time(timestamp):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp)) if timestamp else ''


def info():
    meta = store.catalog_meta()

    db_path = Path(store.DB_PATH)
    db = {'size': 0, 'updated_at': ''}
    if db_path.exists():
        st = db_path.stat()
        db = {'size': st.st_size, 'updated_at': _fmt_time(st.st_mtime)}

    media_dir = Path(store.DATA_DIR) / 'media'
    media_count = 0
    if media_dir.is_dir():
        media_count = sum(1 for p in media_dir.iterdir() if p.is_file())

    backups = []
    backup_dir = Path(store.BACKUP_DIR)
    if backup_dir.is_dir():
        backups = sorted(
            (p for p in backup_dir.glob('*.db') if p.is_file()),
            key=lambda p: p.stat().st_mtime, reverse=True)
    latest = backups[0] if backups else None

    return {
        'version': config.VERSION,
        'data_dir': str(store.DATA_DIR),
        'db': db,
        'media_count': media_count,
        'counts': {
            'products': meta['products'],
            'suppliers': meta['suppliers'],
            'with_image': meta['with_image'],
        },
        'schema': store.schema_info(),
        'backups': {
            'count': len(backups),
            'latest': latest.name if latest else '',
            'latest_at': _fmt_time(latest.stat().st_mtime) if latest else '',
        },
    }
