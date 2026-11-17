# -*- coding: utf-8 -*-
"""全局路径与版本：整个程序只在这里推导目录。

三条边界（P1 立结构，P2 再彻底落地）：
  程序目录（app / tools / web / templates / runtime）—— 只读，可整体替换
  data/                                            —— 用户数据，升级时绝不能被覆盖
  runtime/                                         —— 便携 Python，随包分发
"""
from pathlib import Path
import json

ROOT_PATH = Path(__file__).resolve().parent.parent
ROOT = str(ROOT_PATH)


def _read_version_file():
    """发布包里的 version.json；开发目录没有就回退到内置版本号"""
    try:
        return json.loads((ROOT_PATH / 'version.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


_VERSION_INFO = _read_version_file()

APP_DIR = ROOT_PATH / 'app'
TOOLS_DIR = ROOT_PATH / 'tools'
WEB_ROOT = ROOT_PATH / 'web'
# 前端构建产物存在时优先用它；没有 dist 就用旧页面（迁移期兼容）
WEB_DIR = WEB_ROOT / 'dist' if (WEB_ROOT / 'dist' / 'index.html').is_file() else WEB_ROOT
DATA_DIR = ROOT_PATH / 'data'
TPL_DIR = ROOT_PATH / 'templates'

DB_PATH = DATA_DIR / 'purchase.db'
# 仅用于读取旧版本留下的 data.js（一次性迁移），P2 起不再生成
DATA_JS = WEB_ROOT / 'data.js'
BACKUP_DIR = DATA_DIR / 'backups'


def _read_settings():
    """data/settings.json：本机偏好，缺省或损坏都不影响启动"""
    try:
        return json.loads((DATA_DIR / 'settings.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


_SETTINGS = _read_settings()


def _output_dir():
    value = str(_SETTINGS.get('output_dir') or '').strip()
    if not value:
        return DATA_DIR / 'output'
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT_PATH / path


OUT_DIR = _output_dir()
LOG_PATH = DATA_DIR / 'logs' / 'app.log'
# 产品图片属于用户数据，放 data 下；web/图片 只作为老版本的兼容来源
MEDIA_DIR = DATA_DIR / 'media'
LEGACY_MEDIA_DIR = WEB_ROOT / '图片'

# 合同生成器本体：改了文件要能自动重载，所以按真实路径加载
CONTRACT_DOC_PATH = APP_DIR / 'domain' / 'contract_doc.py'
WEB_INDEX = 'web/dist/index.html' if WEB_DIR == WEB_ROOT / 'dist' else 'web/index.html'


def _stamp_files():
    """程序指纹的文件清单：所有后端源码 + 前端入口"""
    files = [path.relative_to(ROOT_PATH).as_posix() for path in APP_DIR.rglob('*.py')]
    files.append(WEB_INDEX)
    return sorted(files)


# 启动器用来判断"端口上的实例是不是这一份代码"
STAMP_FILES = _stamp_files()

VERSION = str(_VERSION_INFO.get('version') or '2026-11-17')
SCHEMA_VERSION = int(_VERSION_INFO.get('schema_version') or 3)
BUILD_TIME = str(_VERSION_INFO.get('build_time') or '')
