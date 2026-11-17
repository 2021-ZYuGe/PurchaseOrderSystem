# -*- coding: utf-8 -*-
"""构建发布包：程序 + 模板 + 便携运行时 + 快捷方式，不含任何用户数据。

用法：
    python tools/build_release.py
    python tools/build_release.py --no-runtime
    python tools/build_release.py --out D:/release
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

ROOT_FILES = ['start.bat', 'stop.bat', 'maintenance.bat', 'app.ico', 'app.png']
INCLUDE_DIRS = ['app', 'tools', 'templates']
SKIP_DIRS = {'__pycache__', 'node_modules', '.vite'}
SKIP_NAMES = {'data.js', 'data.js.lock', '_icon_preview.png', 'desktop.ini', 'Thumbs.db'}
SKIP_SUFFIXES = {'.pyc', '.pyo', '.log', '.bak', '.tmp', '.db', '.db-wal', '.db-shm'}


def copy_tree(source, target, skip_dirs=SKIP_DIRS):
    copied = 0
    for item in source.rglob('*'):
        if not item.is_file():
            continue
        rel = item.relative_to(source)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if item.name in SKIP_NAMES or item.suffix.lower() in SKIP_SUFFIXES:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)
        copied += 1
    return copied


def copy_web(stage):
    """有构建产物就只发 dist，否则退回旧页面（迁移期）"""
    dist = ROOT / 'web' / 'dist'
    if (dist / 'index.html').is_file():
        return copy_tree(dist, stage / 'web')
    skip = SKIP_DIRS | {'src', 'dist', '_生成合同', '图片'}
    return copy_tree(ROOT / 'web', stage / 'web', skip_dirs=skip)


def check_frontend():
    """改了前端源码却忘记构建时，直接拒绝出包"""
    index = ROOT / 'web' / 'dist' / 'index.html'
    source = ROOT / 'web' / 'src'
    if not source.is_dir():
        return []
    if not index.is_file():
        return ['没有 web/dist，请先运行 npm run build']
    newest = max((p.stat().st_mtime for p in source.rglob('*') if p.is_file()), default=0)
    if newest > index.stat().st_mtime + 1:
        return ['web/dist 比 web/src 旧，请先运行 npm run build']
    return []


def write_readme(stage, version):
    text = '''采购下单系统 v%s

第一次使用

1. 解压到一个有写入权限的位置（不要放 C:/Program Files）。
2. 双击「采购下单系统」快捷方式；快捷方式丢了就双击 start.bat。
3. 浏览器会打开导入向导：选择你从易快报导出的合同文件夹，开始导入。
4. 导入完成后自动进入系统；以后双击快捷方式即可。

升级到新版本

1. 把新版本解压到另一个文件夹（不要覆盖旧文件夹）。
2. 把旧文件夹里的 data 目录整个复制到新文件夹。
3. 双击新文件夹的 start.bat，数据库结构会自动升级。
4. 确认数据正常后，再删除旧文件夹。

数据与备份

所有数据都在 data 目录，不会上传到任何服务器；升级只换程序，不动 data。
每天首次启动会自动备份数据库到 data/backups（保留最近 7 份）。
换电脑：旧电脑「系统状态 → 导出数据包」，新电脑首次向导里选这个 zip 恢复。
关闭系统：直接关掉浏览器页面；页面关不掉时双击 stop.bat。
''' % version
    (stage / 'README.txt').write_bytes(text.replace('\n', '\r\n').encode('utf-8-sig'))


def build(out_dir, with_runtime=True):
    problems = check_frontend()
    if problems:
        raise SystemExit('；'.join(problems))

    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / ('purchase-order-v%s' % config.VERSION)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    copied = 0
    for name in ROOT_FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, stage / name)
            copied += 1

    for dirname in INCLUDE_DIRS:
        source = ROOT / dirname
        if not source.is_dir():
            raise SystemExit('缺少目录：%s' % source)
        copied += copy_tree(source, stage / dirname)

    copied += copy_web(stage)

    if with_runtime:
        runtime = ROOT / 'runtime'
        if not runtime.is_dir():
            raise SystemExit('缺少 runtime 目录')
        copied += copy_tree(runtime, stage / 'runtime')

    meta = {
        'version': config.VERSION,
        'schema_version': int(store.SCHEMA_VERSION),
        'build_time': time.strftime('%Y-%m-%d %H:%M'),
        'with_runtime': with_runtime,
    }
    (stage / 'version.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    write_readme(stage, config.VERSION)

    if with_runtime:
        sys.path.insert(0, str(ROOT / 'tools'))
        import make_shortcut
        make_shortcut.build(stage)

    return stage, copied, meta


def verify(stage, with_runtime=True):
    problems = []
    names = [path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file()]
    lowered = [name.lower() for name in names]
    if any(name.startswith('data/') for name in lowered):
        problems.append('包含 data/ 用户数据')
    if any(name.startswith('web/src/') for name in lowered):
        problems.append('包含前端源码 web/src')
    if any('node_modules' in name for name in lowered):
        problems.append('包含 node_modules')
    if any('__pycache__' in name for name in lowered):
        problems.append('包含 __pycache__')
    required = ['app/config.py', 'app/api/app.py', 'web/index.html',
                'start.bat', 'templates/主合同-一次性发货.docx', 'version.json',
                'README.txt']
    if with_runtime:
        required += ['采购下单系统.lnk']
    for name in required:
        if name not in names:
            problems.append('缺少 %s' % name)
    if with_runtime and 'runtime/python.exe' not in names:
        problems.append('缺少 runtime/python.exe')
    return problems


def pack(stage, out_dir):
    zip_path = Path(out_dir) / (stage.name + '.zip')
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in stage.rglob('*'):
            if path.is_file():
                archive.write(path, stage.name + '/' + path.relative_to(stage).as_posix())
    return zip_path


def main():
    parser = argparse.ArgumentParser(description='构建采购下单系统发布包')
    parser.add_argument('--out', default=str(ROOT / 'dist'), help='输出目录，默认 dist/')
    parser.add_argument('--no-runtime', action='store_true', help='不打包便携 Python')
    args = parser.parse_args()

    started = time.time()
    stage, copied, meta = build(args.out, with_runtime=not args.no_runtime)
    problems = verify(stage, with_runtime=not args.no_runtime)
    if problems:
        print('[校验未通过]')
        for item in problems:
            print('  - ' + item)
        return 1

    zip_path = pack(stage, Path(args.out))
    size = zip_path.stat().st_size / 1024 / 1024
    print('目录：%s（%d 个文件）' % (stage, copied))
    print('发布包：%s（%.1f MB，用时 %.0f 秒）' % (zip_path, size, time.time() - started))
    print('版本：%s / 数据结构 v%s' % (meta['version'], meta['schema_version']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
