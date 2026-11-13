# -*- coding: utf-8 -*-
"""首次启动向导：导入合同、选择文件夹、从数据库备份恢复。

导入复用现有的解析器子进程（工具/_工具_生成数据库.py），
服务端只负责传路径、读进度、报结果，不重复实现解析逻辑。
"""
import ctypes
import os
import re
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import time
from ctypes import wintypes
from pathlib import Path

import app.config as config
from app.infra import media, store
from app.infra.logging import log

MAX_RESTORE_BYTES = 60 * 1024 * 1024
MAX_PACKAGE_BYTES = 200 * 1024 * 1024

_LOCK = threading.Lock()
_STATE = {
    'state': 'idle',        # idle / running / done / error
    'message': '',
    'error': '',
    'done': 0,
    'total': 0,
    'started': '',
    'finished': '',
}


def _set(**kw):
    with _LOCK:
        _STATE.update(kw)


def status():
    with _LOCK:
        data = dict(_STATE)
    data['products'] = store.product_count()
    data['need_setup'] = data['products'] == 0
    return data


def import_contracts(folder):
    """校验路径后启动后台导入；同一时间只允许一个导入任务"""
    path = str(folder or '').strip().strip('"').strip("'")
    if not path:
        return {'ok': False, 'error': '请先选择合同文件夹'}
    target = Path(path)
    if not target.is_dir():
        return {'ok': False, 'error': '找不到这个文件夹：%s' % path}
    try:
        docs = sum(1 for _ in target.rglob('*.docx'))
    except OSError as e:
        return {'ok': False, 'error': '读取文件夹失败：%s' % e}
    if docs == 0:
        return {'ok': False, 'error': '这个文件夹里没有 .docx 合同'}

    with _LOCK:
        if _STATE['state'] == 'running':
            return {'ok': False, 'error': '正在导入，请稍候'}
        _STATE.update({
            'state': 'running', 'message': '共 %d 份合同，正在解析…' % docs, 'error': '',
            'done': 0, 'total': docs,
            'started': time.strftime('%H:%M:%S'), 'finished': '',
        })
    threading.Thread(target=_import_worker, args=(target,), daemon=True).start()
    return {'ok': True}


def _import_worker(folder):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    cmd = [sys.executable, str(config.TOOLS_DIR / '_工具_生成数据库.py'), str(folder)]
    tail = []
    try:
        proc = subprocess.Popen(
            cmd, cwd=config.ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in iter(proc.stdout.readline, b''):
            line = raw.decode('utf-8', 'replace').strip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-8:]
            m = re.search(r'已处理\s*(\d+)\s*/\s*(\d+)', line)
            if m:
                _set(done=int(m.group(1)), total=int(m.group(2)),
                     message='正在解析合同（%s/%s）…' % (m.group(1), m.group(2)))
            elif '解析完成' in line or '提取产品' in line:
                _set(message=line)
        code = proc.wait()
        if code == 0 and store.product_count() > 0:
            media.ensure_migrated()
            _set(state='done', finished=time.strftime('%H:%M:%S'),
                 message='导入完成：产品 %d 个，供应商 %d 家'
                         % (store.product_count(), len(store.list_suppliers_light())))
            log('首次导入完成：%s' % folder)
        else:
            reason = tail[-1] if tail else ('解析器返回码 %s' % code)
            _set(state='error', error=reason, finished=time.strftime('%H:%M:%S'),
                 message='导入失败')
            log('首次导入失败（%s）：%s' % (folder, reason))
    except Exception as e:
        _set(state='error', error='%s' % e, finished=time.strftime('%H:%M:%S'),
             message='导入失败')
        log('首次导入异常：%r' % (e,))


def pick_folder():
    """弹出 Windows 原生「选择文件夹」对话框；取消返回空串。

    没有 tkinter，所以直接用 shell32 的 SHBrowseForFolderW。
    """
    if os.name != 'nt':
        return ''
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        class BROWSEINFOW(ctypes.Structure):
            _fields_ = [
                ('hwndOwner', wintypes.HWND),
                ('pidlRoot', ctypes.c_void_p),
                ('pszDisplayName', wintypes.LPWSTR),
                ('lpszTitle', wintypes.LPCWSTR),
                ('ulFlags', wintypes.UINT),
                ('lpfn', ctypes.c_void_p),
                ('lParam', wintypes.LPARAM),
                ('iImage', ctypes.c_int),
            ]

        shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
        shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
        shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
        shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

        ole32.CoInitialize(None)
        try:
            display = ctypes.create_unicode_buffer(1024)
            bi = BROWSEINFOW()
            bi.hwndOwner = user32.GetForegroundWindow()
            bi.pszDisplayName = ctypes.cast(display, wintypes.LPWSTR)
            bi.lpszTitle = '选择存放合同的文件夹'
            # 只允许文件系统目录 + 新样式（可拖动、可新建）+ 可手动输入路径
            bi.ulFlags = 0x0001 | 0x0040 | 0x0010
            pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
            if not pidl:
                return ''
            try:
                path_buf = ctypes.create_unicode_buffer(2048)
                if not shell32.SHGetPathFromIDListW(pidl, path_buf):
                    return ''
                return path_buf.value
            finally:
                ole32.CoTaskMemFree(pidl)
        finally:
            ole32.CoUninitialize()
    except Exception as e:
        log('选择文件夹对话框失败：%r' % (e,))
        return ''


def _check_db_file(path):
    """校验 sqlite 文件；返回错误字符串，没问题返回空串"""
    try:
        conn = sqlite3.connect(str(path))
        try:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'").fetchone() \
                if 'schema_meta' in tables else None
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return '这不是有效的数据库文件'
    if integrity != 'ok':
        return '数据库校验失败：%s' % integrity
    if not {'products', 'suppliers'}.issubset(tables):
        return '这个文件不是本系统的数据库'
    version = int(row[0]) if row else 0
    if version > int(store.SCHEMA_VERSION):
        return '备份来自更新版本（数据 v%d），请升级程序后再恢复' % version
    return ''


def _apply_db_file(path):
    """覆盖当前库（先自动备份），并完成迁移与缓存清理"""
    if Path(store.DB_PATH).exists():
        store.backup_database('before_restore')
    store.restore_database(str(path))
    store.ensure_database()
    store.clear_pending_cache()


def restore_database(raw_bytes):
    """从单个 .db 字节恢复"""
    if not raw_bytes:
        return {'ok': False, 'error': '没有收到文件'}
    if len(raw_bytes) > MAX_RESTORE_BYTES:
        return {'ok': False, 'error': '文件太大（超过 %dMB）' % (MAX_RESTORE_BYTES // 1024 // 1024)}

    tmp_dir = Path(tempfile.mkdtemp(prefix='restore_'))
    tmp = tmp_dir / 'restore.db'
    try:
        tmp.write_bytes(raw_bytes)
        error = _check_db_file(tmp)
        if error:
            return {'ok': False, 'error': error}
        _apply_db_file(tmp)
        media.ensure_migrated()
        log('已从上传的数据库恢复：产品 %d 个' % store.product_count())
        return {'ok': True, 'products': store.product_count(), 'media': 0}
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def restore_package(raw_bytes):
    """从数据包（zip：purchase.db + media/）恢复"""
    if len(raw_bytes) > MAX_PACKAGE_BYTES:
        return {'ok': False, 'error': '数据包太大（超过 %dMB）'
                % (MAX_PACKAGE_BYTES // 1024 // 1024)}
    tmp_dir = Path(tempfile.mkdtemp(prefix='restore_pkg_'))
    tmp_zip = tmp_dir / 'package.zip'
    try:
        tmp_zip.write_bytes(raw_bytes)
        try:
            zf = zipfile.ZipFile(tmp_zip)
        except zipfile.BadZipFile:
            return {'ok': False, 'error': '这不是有效的数据包（zip）'}

        with zf:
            names = zf.namelist()
            db_member = next((n for n in names
                              if n == 'purchase.db' or n.endswith('/purchase.db')), None)
            if not db_member:
                return {'ok': False, 'error': '数据包里没有 purchase.db'}
            db_file = tmp_dir / 'purchase.db'
            with zf.open(db_member) as src, open(db_file, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            error = _check_db_file(db_file)
            if error:
                return {'ok': False, 'error': error}

            _apply_db_file(db_file)

            media_dir = Path(store.DATA_DIR) / 'media'
            media_dir.mkdir(parents=True, exist_ok=True)
            copied = 0
            for name in names:
                if not name.startswith('media/') or name.endswith('/'):
                    continue
                filename = Path(name).name
                if not filename:
                    continue
                target = media_dir / filename
                try:
                    with zf.open(name) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    copied += 1
                except OSError:
                    continue
        log('已从数据包恢复：产品 %d 个，图片 %d 张' % (store.product_count(), copied))
        return {'ok': True, 'products': store.product_count(), 'media': copied}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def restore_any(raw_bytes):
    """按文件头判断是数据库还是数据包"""
    if raw_bytes[:4] == b'PK\x03\x04':
        return restore_package(raw_bytes)
    return restore_database(raw_bytes)
