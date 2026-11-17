# -*- coding: utf-8 -*-
"""维护菜单：停止服务、清缓存、看日志、重建快捷方式、比对合同。

由 maintenance.bat 调用；不常驻，不修改业务数据。
"""
import difflib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_CANDIDATES = [ROOT / 'data' / 'logs' / 'app.log', ROOT / 'data' / '_运行日志.txt']
SKIP_DIRS = {'runtime', 'data', '.git', 'node_modules'}


def _pause():
    try:
        input('\n按回车继续…')
    except EOFError:
        pass


def stop_service():
    import stop
    stop.stop_all()


def clean_caches():
    removed = 0
    for current, dirs, _files in os.walk(ROOT):
        parts = Path(current).parts
        if any(part in SKIP_DIRS for part in parts):
            dirs[:] = []
            continue
        for name in list(dirs):
            if name == '__pycache__':
                shutil.rmtree(Path(current) / name, ignore_errors=True)
                dirs.remove(name)
                removed += 1
    print('已清理 %d 个 __pycache__ 目录。' % removed)


def show_log():
    path = next((p for p in LOG_CANDIDATES if p.is_file()), None)
    if not path:
        print('还没有日志文件。')
        return
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    print('日志：%s（最后 30 行）\n' % path)
    print('\n'.join(lines[-30:]))


def rebuild_shortcut():
    import make_shortcut
    make_shortcut.main()


def compare_docs():
    from docx_diff import snapshot
    first = input('旧文件路径：').strip().strip('"')
    second = input('新文件路径：').strip().strip('"')
    if not (os.path.isfile(first) and os.path.isfile(second)):
        print('文件不存在。')
        return
    diff = list(difflib.unified_diff(
        snapshot(Path(first)), snapshot(Path(second)),
        fromfile=first, tofile=second, lineterm=''))
    if not diff:
        print('\n内容一致。')
        return
    print('\n'.join(diff))
    print('\n共 %d 行差异。' % sum(1 for line in diff if line[:1] in '+-'))


MENU = [
    ('1', '停止系统', stop_service),
    ('2', '清理缓存', clean_caches),
    ('3', '查看日志', show_log),
    ('4', '重建快捷方式', rebuild_shortcut),
    ('5', '比对两份合同', compare_docs),
    ('0', '退出', None),
]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    while True:
        print('\n采购下单系统 · 维护')
        for key, label, _ in MENU:
            print('  %s. %s' % (key, label))
        choice = input('请选择：').strip()
        action = next((fn for key, _, fn in MENU if key == choice), 'invalid')
        if action == 'invalid':
            print('没有这个选项。')
            continue
        if action is None:
            return 0
        try:
            action()
        except Exception as exc:
            print('执行失败：%s' % exc)
        _pause()


if __name__ == '__main__':
    sys.exit(main())
