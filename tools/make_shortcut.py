# -*- coding: utf-8 -*-
"""生成「采购下单系统」快捷方式（调用系统 IShellLink，不依赖第三方库）。

快捷方式放在程序根目录，目标为 runtime\\pythonw.exe -m app：
  - pythonw 不弹控制台
  - 写入相对路径，整个文件夹搬走后仍能启动
  - 图标用 assets/app.ico

用法：
    python tools/make_shortcut.py
"""
import ctypes
import os
import sys
import uuid
from ctypes import (HRESULT, POINTER, byref, c_int, c_ubyte, c_uint16,
                    c_uint32, c_void_p, c_wchar_p)
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'runtime' / 'pythonw.exe'
FALLBACK = ROOT / 'runtime' / 'python.exe'
ICON = ROOT / 'assets' / 'app.ico'
LNK = ROOT / '采购下单系统.lnk'
ARGS = '-m app'
DESC = '采购下单系统（关闭网页后自动退出）'

ole32 = ctypes.WinDLL('ole32')


class GUID(ctypes.Structure):
    _fields_ = [('Data1', c_uint32), ('Data2', c_uint16),
                ('Data3', c_uint16), ('Data4', c_ubyte * 8)]


def _guid(text):
    value = GUID()
    ctypes.memmove(byref(value), uuid.UUID(text).bytes_le, 16)
    return value


def _call(ptr, index, restype, argtypes, *args):
    """按 vtable 下标调用 COM 方法"""
    vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
    func = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[index])
    result = func(ptr, *args)
    if isinstance(result, int) and result < 0:
        raise OSError('COM 调用失败 0x%08X (方法 %d)' % (result & 0xFFFFFFFF, index))
    return result


def make_shortcut(lnk_path, target, args, workdir, icon, desc, relpath=None):
    clsctx_inproc = 1
    clsid = _guid('{00021401-0000-0000-C000-000000000046}')
    iid_link = _guid('{000214F9-0000-0000-C000-000000000046}')
    iid_file = _guid('{0000010B-0000-0000-C000-000000000046}')

    ole32.CoInitialize(None)
    shell_link = c_void_p()
    ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, c_uint32,
                                       POINTER(GUID), POINTER(c_void_p)]
    ole32.CoCreateInstance.restype = HRESULT
    code = ole32.CoCreateInstance(byref(clsid), None, clsctx_inproc,
                                  byref(iid_link), byref(shell_link))
    if code < 0:
        raise OSError('无法创建 ShellLink 0x%08X' % (code & 0xFFFFFFFF))

    try:
        _call(shell_link, 20, HRESULT, [c_wchar_p], str(target))          # SetPath
        if relpath:
            _call(shell_link, 18, HRESULT, [c_wchar_p, c_uint32], relpath, 0)
        if args:
            _call(shell_link, 11, HRESULT, [c_wchar_p], args)             # SetArguments
        if workdir:
            _call(shell_link, 9, HRESULT, [c_wchar_p], str(workdir))      # SetWorkingDirectory
        if desc:
            _call(shell_link, 7, HRESULT, [c_wchar_p], desc)              # SetDescription
        if icon:
            _call(shell_link, 17, HRESULT, [c_wchar_p, c_int], str(icon), 0)
        _call(shell_link, 15, HRESULT, [c_int], 1)                        # SetShowCmd

        persist = c_void_p()
        _call(shell_link, 0, HRESULT, [POINTER(GUID), POINTER(c_void_p)],
              byref(iid_file), byref(persist))                            # QueryInterface
        try:
            _call(persist, 6, HRESULT, [c_wchar_p, c_int], str(lnk_path), 1)
        finally:
            if persist:
                _call(persist, 2, ctypes.c_ulong, [])
    finally:
        if shell_link:
            _call(shell_link, 2, ctypes.c_ulong, [])
        ole32.CoUninitialize()


def build(root=ROOT):
    """在指定目录生成快捷方式；构建发布包时传入暂存目录"""
    root = Path(root).resolve()
    target = root / 'runtime' / 'pythonw.exe'
    if not target.is_file():
        target = root / 'runtime' / 'python.exe'
    if not target.is_file():
        print('找不到 runtime\\pythonw.exe，请确认程序目录完整。')
        return None

    lnk = root / LNK.name
    if lnk.exists():
        lnk.unlink()

    relpath = os.path.relpath(str(target), str(root))
    icon = root / 'assets' / 'app.ico'
    make_shortcut(lnk, target, ARGS, root,
                  icon if icon.is_file() else '', DESC, relpath)
    return lnk


def main():
    lnk = build(ROOT)
    if not lnk:
        return 1
    print('已生成：%s' % lnk)
    print('工作目录：%s' % ROOT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
