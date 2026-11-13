# -*- coding: utf-8 -*-
"""生成「采购下单系统」快捷方式（ctypes 调用系统 IShellLink，不依赖第三方库）

只生成 .lnk，全程不碰 desktop.ini。

旧版本为了让文件夹本身也用品牌图标，会在项目根写 desktop.ini 并把文件夹设成
“系统属性”——这套动作跟木马伪装文件夹一模一样，360 的“文件夹伪装”防护每次都
会弹“有程序试图修改 Desktop.ini”。文件夹外观已确认不需要，相关代码整段删除，
以后不可能再写这个文件。

每次运行还会顺手清掉旧版留下的 desktop.ini 并摘掉目录的系统属性；已经干净时
不做任何写操作。

    运行环境\\python.exe 工具\\_创建快捷方式.py               重建快捷方式（顺带清理）
    运行环境\\python.exe 工具\\_创建快捷方式.py --clean-only   只清理，不重建
"""
import ctypes
import os
import sys
import uuid
from ctypes import HRESULT, POINTER, byref, c_int, c_ubyte, c_uint16, c_uint32, c_void_p, c_wchar_p

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, '运行环境', 'pythonw.exe')
SCRIPT = os.path.join(ROOT, '工具', '打开系统_静默.py')
ICON = os.path.join(ROOT, '采购合同下单系统.ico')
DESC = '采购合同下单系统（关掉网页后自动退出）'
LNK_NAME = '采购合同下单系统.lnk'

FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
FILE_ATTRIBUTE_NORMAL = 0x80

ole32 = ctypes.WinDLL('ole32')


class GUID(ctypes.Structure):
    _fields_ = [('Data1', c_uint32), ('Data2', c_uint16),
                ('Data3', c_uint16), ('Data4', c_ubyte * 8)]


def guid(s):
    g = GUID()
    ctypes.memmove(byref(g), uuid.UUID(s).bytes_le, 16)
    return g


def call(ptr, index, restype, argtypes, *args):
    """按 vtable 下标调用 COM 方法"""
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])
    hr = fn(ptr, *args)
    if isinstance(hr, int) and hr < 0:
        raise OSError('COM 调用失败 0x%08X (方法 %d)' % (hr & 0xFFFFFFFF, index))
    return hr


def desktop_dir():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
    return buf.value or os.path.join(os.environ['USERPROFILE'], 'Desktop')


def make_shortcut(lnk_path, target, args, workdir, icon, desc, relpath=None):
    CLSCTX_INPROC_SERVER = 1
    clsid = guid('{00021401-0000-0000-C000-000000000046}')
    iid_link = guid('{000214F9-0000-0000-C000-000000000046}')
    iid_file = guid('{0000010B-0000-0000-C000-000000000046}')

    ole32.CoInitialize(None)
    psl = c_void_p()
    ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, c_uint32,
                                       POINTER(GUID), POINTER(c_void_p)]
    ole32.CoCreateInstance.restype = HRESULT
    hr = ole32.CoCreateInstance(byref(clsid), None, CLSCTX_INPROC_SERVER,
                                byref(iid_link), byref(psl))
    if hr < 0:
        raise OSError('无法创建 ShellLink 0x%08X' % (hr & 0xFFFFFFFF))

    try:
        call(psl, 20, HRESULT, [c_wchar_p], target)              # SetPath
        if relpath:
            # 文件夹整体搬走后，Windows 可凭相对路径找回目标
            call(psl, 18, HRESULT, [c_wchar_p, c_uint32], relpath, 0)
        if args:
            call(psl, 11, HRESULT, [c_wchar_p], args)            # SetArguments
        if workdir:
            call(psl, 9, HRESULT, [c_wchar_p], workdir)          # SetWorkingDirectory
        if desc:
            call(psl, 7, HRESULT, [c_wchar_p], desc)             # SetDescription
        if icon:
            call(psl, 17, HRESULT, [c_wchar_p, c_int], icon, 0)  # SetIconLocation
        call(psl, 15, HRESULT, [c_int], 1)                       # SetShowCmd 普通窗口

        pfile = c_void_p()
        call(psl, 0, HRESULT, [POINTER(GUID), POINTER(c_void_p)],
             byref(iid_file), byref(pfile))                      # QueryInterface
        try:
            call(pfile, 6, HRESULT, [c_wchar_p, c_int], lnk_path, 1)  # IPersistFile::Save
        finally:
            if pfile:
                call(pfile, 2, ctypes.c_ulong, [])               # Release
    finally:
        if psl:
            call(psl, 2, ctypes.c_ulong, [])                     # Release
        ole32.CoUninitialize()


def get_attrs(path):
    """读文件/目录属性位，读不到返回 -1"""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetFileAttributesW.argtypes = [c_wchar_p]
    k32.GetFileAttributesW.restype = c_uint32
    cur = k32.GetFileAttributesW(path)
    return -1 if cur == 0xFFFFFFFF else cur


def clear_attrs(path, flags):
    """摘掉指定的属性位，别的位保留"""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetFileAttributesW.argtypes = [c_wchar_p]
    k32.GetFileAttributesW.restype = c_uint32
    k32.SetFileAttributesW.argtypes = [c_wchar_p, c_uint32]
    k32.SetFileAttributesW.restype = c_int
    cur = k32.GetFileAttributesW(path)
    if cur == 0xFFFFFFFF:
        return False
    return bool(k32.SetFileAttributesW(path, cur & ~flags))


def clear_ro_attrs(path):
    """写之前先摘掉只读/隐藏/系统，否则 Windows 直接拒绝覆盖写入"""
    clear_attrs(path, FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)


def _refresh_dir():
    """通知资源管理器刷新这个目录的图标，不弹任何窗口"""
    try:
        ctypes.WinDLL('shell32').SHChangeNotify(0x00001000, 0x0005, c_wchar_p(ROOT), None)
    except Exception:
        pass


def restore_folder_appearance():
    """清掉旧版留下的 desktop.ini 和目录的系统属性

    返回 'removed' 删掉了 ini / 'cleaned' 没 ini 但摘了目录属性
       / 'none' 本来就干净（不产生任何写操作） / 'failed' 删不掉
    """
    ini = os.path.join(ROOT, 'desktop.ini')
    if os.path.isfile(ini):
        clear_ro_attrs(ini)
        try:
            os.remove(ini)
        except Exception:
            return 'failed'
        clear_attrs(ROOT, FILE_ATTRIBUTE_SYSTEM)
        _refresh_dir()
        return 'removed'

    if get_attrs(ROOT) & FILE_ATTRIBUTE_SYSTEM:
        clear_attrs(ROOT, FILE_ATTRIBUTE_SYSTEM)
        _refresh_dir()
        return 'cleaned'
    return 'none'


def main():
    args = [a.lower() for a in sys.argv[1:]]
    clean_only = '--clean-only' in args

    # 先把手尾清干净：旧版写过 desktop.ini，删掉；本来就没有则不做任何写操作
    st = restore_folder_appearance()
    if st == 'removed':
        print('文件夹外观: 已删除旧版留下的 desktop.ini，恢复系统默认')
    elif st == 'cleaned':
        print('文件夹外观: 已摘掉目录的系统属性，恢复系统默认')
    elif st == 'failed':
        print('文件夹外观: 旧版 desktop.ini 删不掉（可能被资源管理器占用），重启后再试')
        if clean_only:
            return 1

    if clean_only:
        print('（只做清理，快捷方式没有改动）')
        return 0

    if not os.path.isfile(TARGET):
        print('找不到 pythonw.exe:', TARGET)
        return 1
    if not os.path.isfile(SCRIPT):
        print('找不到启动脚本:', SCRIPT)
        return 1

    # 快捷方式放在项目根目录，随文件夹一起打包搬走
    lnk = os.path.join(ROOT, LNK_NAME)
    if os.path.exists(lnk):
        os.remove(lnk)

    lnk_args = '"%s"' % SCRIPT
    relpath = os.path.relpath(TARGET, os.path.dirname(lnk))
    # 注意：图标路径不能拼 ",0"，索引由 SetIconLocation 的第二个参数单独传，
    # 拼进去会变成文件名的一部分，资源管理器找不到就退化成白纸图标。
    make_shortcut(lnk, TARGET, lnk_args, ROOT,
                  ICON if os.path.isfile(ICON) else '', DESC, relpath)

    print('已生成:', lnk)
    print('大小: %d 字节' % os.path.getsize(lnk))
    print('目标:', TARGET)
    print('参数:', lnk_args)
    print('工作目录:', ROOT)
    print('相对路径: %s' % relpath)
    print('文件夹外观: 系统默认（本脚本不再写 desktop.ini，不会触发安全软件提示）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
