# -*- coding: utf-8 -*-
"""构建空白发布包：程序 + 便携 Python + 合同模板，不含任何用户数据。

用法：
    python 工具/构建发布包.py                  # 完整包（含运行环境）
    python 工具/构建发布包.py --no-runtime     # 快速验证（体积小，用本机 Python 跑）
    python 工具/构建发布包.py --out D:/发布     # 指定输出目录

产物：
    dist/采购下单系统_v<版本>.zip
"""
import argparse
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.config as config
from app.infra import store

ROOT_FILES = [
    '启动网页版.bat',
    '关闭系统.bat',
    '扫描合同并更新数据库.bat',
    '一键自检清理.bat',
    '重建快捷方式.bat',
    '采购合同下单系统.ico',
    '采购合同下单系统.png',
]

INCLUDE_DIRS = ['app', '工具', 'web', '合同模板']
OPTIONAL_DIRS = ['运行环境']

EXCLUDE_ROOT_DIRS = {'data', 'dist', 'tests', '.git', '.workbuddy'}
EXCLUDE_WEB_DIRS = {'图片', '_生成合同'}
EXCLUDE_NAMES = {'data.js', 'data.js.lock', '_icon_preview.png', 'desktop.ini', 'Thumbs.db'}
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.log', '.bak', '.tmp', '.db'}


def iter_files(base):
    for path in base.rglob('*'):
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if rel.parts[0] in EXCLUDE_ROOT_DIRS:
            continue
        if '__pycache__' in rel.parts:
            continue
        if rel.parts[0] == 'web' and len(rel.parts) > 2 and rel.parts[1] in EXCLUDE_WEB_DIRS:
            continue
        if path.name in EXCLUDE_NAMES:
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        yield path, rel


def build(out_dir, with_runtime=True):
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / ('采购下单系统_v%s' % config.VERSION)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    copied = 0
    for name in ROOT_FILES:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, stage / name)
            copied += 1

    dirs = list(INCLUDE_DIRS) + (OPTIONAL_DIRS if with_runtime else [])
    for dirname in dirs:
        base = ROOT / dirname
        if not base.is_dir():
            raise SystemExit('缺少目录：%s' % base)
        for src, rel in iter_files(base):
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            copied += 1

    meta = {
        'version': config.VERSION,
        'schema_version': int(store.SCHEMA_VERSION),
        'build_time': time.strftime('%Y-%m-%d %H:%M'),
        'with_runtime': with_runtime,
    }
    (stage / 'version.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8', newline='\n')

    readme = '''采购下单系统 · 首次使用

1. 解压到一个有写入权限的位置（不要放 C:\\Program Files）。
2. 双击「启动网页版.bat」。
3. 浏览器会打开发布向导：选择你从易快报导出的合同文件夹 → 开始导入。
4. 导入完成后自动进入系统；以后双击「启动网页版.bat」即可。

数据保存在 data 目录，升级程序不会覆盖；备份在 data\\backups。
关闭系统：双击「关闭系统.bat」。
'''
    (stage / '首次使用.txt').write_bytes(readme.replace('\n', '\r\n').encode('gbk'))

    zip_path = out_dir / ('采购下单系统_v%s.zip' % config.VERSION)
    if zip_path.exists():
        zip_path.unlink()
    # 压缩包里保留一层根目录：解压到已有文件夹时不会散落一地
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in stage.rglob('*'):
            if path.is_file():
                zf.write(path, (stage.name + '/' + path.relative_to(stage).as_posix()))

    return stage, zip_path, copied, meta


def verify(zip_path, with_runtime):
    problems = []
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.namelist()
    tops = {n.split('/', 1)[0] for n in raw if '/' in n}
    prefix = next(iter(tops)) + '/' if len(tops) == 1 else ''
    names = [n[len(prefix):] for n in raw]
    lowered = [n.lower() for n in names]
    if any(n.startswith('data/') for n in lowered):
        problems.append('包含 data/ 用户数据')
    if any(n.startswith('web/图片/') for n in names):
        problems.append('包含 web/图片（应放到 data/media）')
    if any(n.startswith('web/_生成合同/') for n in names):
        problems.append('包含历史生成合同')
    if any('__pycache__' in n for n in lowered):
        problems.append('包含 __pycache__')
    for must in ('app/config.py', 'app/api/server.py', 'web/index.html',
                 'web/welcome.html', 'web/js/app-main.js', 'version.json',
                 '合同模板/主合同-一次性发货.docx'):
        if must not in names:
            problems.append('缺少 %s' % must)
    if with_runtime and '运行环境/python.exe' not in names:
        problems.append('缺少 运行环境/python.exe')
    return problems


def main():
    ap = argparse.ArgumentParser(description='构建采购下单系统空白发布包')
    ap.add_argument('--out', default=str(ROOT / 'dist'), help='输出目录，默认 dist/')
    ap.add_argument('--no-runtime', action='store_true', help='不打包便携 Python（快速验证用）')
    ap.add_argument('--no-zip', action='store_true', help='只生成目录，不压缩')
    args = ap.parse_args()

    started = time.time()
    stage, zip_path, copied, meta = build(args.out, with_runtime=not args.no_runtime)
    print('目录已生成：%s（%d 个文件）' % (stage, copied))
    if args.no_zip:
        return 0
    problems = verify(zip_path, with_runtime=not args.no_runtime)
    size = zip_path.stat().st_size / 1024 / 1024
    print('发布包：%s（%.1f MB，用时 %.0f 秒）' % (zip_path, size, time.time() - started))
    print('版本：%s / 数据结构 v%s' % (meta['version'], meta['schema_version']))
    if problems:
        print('\n[校验未通过]')
        for p in problems:
            print('  - ' + p)
        return 1
    print('校验通过：不含 data/、web/图片、历史合同与缓存')
    return 0


if __name__ == '__main__':
    sys.exit(main())
