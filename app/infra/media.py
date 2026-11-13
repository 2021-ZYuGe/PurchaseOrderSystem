# -*- coding: utf-8 -*-
"""产品图片：统一放在 data/media/，与程序目录解耦。

历史版本把图片写在 web/图片/ 下，升级程序或换电脑时容易丢。
P2 起新图片一律写 data/media；老的 web/图片 只读兼容，首次启动复制过去。
"""
import mimetypes
import os
import shutil

from app.config import LEGACY_MEDIA_DIR, MEDIA_DIR


def ensure_dir():
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


def ensure_migrated():
    """把 web/图片 里还缺的文件复制到 data/media，幂等。

    只复制不删除：老目录保留一个版本，确认没问题后再由发布流程排除。
    """
    ensure_dir()
    if not LEGACY_MEDIA_DIR.is_dir():
        return 0
    copied = 0
    for src in LEGACY_MEDIA_DIR.iterdir():
        if not src.is_file():
            continue
        dst = MEDIA_DIR / src.name
        if dst.exists():
            continue
        try:
            shutil.copy2(src, dst)
            copied += 1
        except OSError:
            continue
    return copied


def resolve(name):
    """按文件名取图片；拒绝任何带路径分隔符的输入。"""
    safe = os.path.basename(str(name or ''))
    if not safe or safe != str(name).strip():
        return None
    candidate = MEDIA_DIR / safe
    if candidate.is_file():
        return candidate
    legacy = LEGACY_MEDIA_DIR / safe
    if legacy.is_file():
        return legacy
    return None


def content_type(path):
    return mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
