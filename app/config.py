# -*- coding: utf-8 -*-
"""全局路径与版本：整个程序只在这里推导目录。

三条边界（P1 立结构，P2 再彻底落地）：
  程序目录（app / 工具 / web / 合同模板 / 运行环境）—— 只读，可整体替换
  data/                                            —— 用户数据，升级时绝不能被覆盖
  运行环境/                                         —— 便携 Python，随包分发
"""
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parent.parent
ROOT = str(ROOT_PATH)

APP_DIR = ROOT_PATH / 'app'
TOOLS_DIR = ROOT_PATH / '工具'
WEB_DIR = ROOT_PATH / 'web'
DATA_DIR = ROOT_PATH / 'data'
TPL_DIR = ROOT_PATH / '合同模板'

DB_PATH = DATA_DIR / 'purchase.db'
# 仅用于读取旧版本留下的 data.js（一次性迁移），P2 起不再生成
DATA_JS = WEB_DIR / 'data.js'
BACKUP_DIR = DATA_DIR / 'backups'
OUT_DIR = WEB_DIR / '_生成合同'
LOG_PATH = DATA_DIR / '_运行日志.txt'
# 产品图片属于用户数据，放 data 下；web/图片 只作为老版本的兼容来源
MEDIA_DIR = DATA_DIR / 'media'
LEGACY_MEDIA_DIR = WEB_DIR / '图片'

# 一键更新时拉起的子进程脚本（P5 会改成服务内调用）
MERGE_SCRIPT = TOOLS_DIR / '合并新合同.py'
# 合同生成器本体：改了文件要能自动重载，所以按真实路径加载
CONTRACT_DOC_PATH = APP_DIR / 'domain' / 'contract_doc.py'

# 启动器用来判断"端口上的实例是不是这一份代码"
STAMP_FILES = [
    'app/api/server.py',
    'app/api/routes.py',
    'app/domain/contract_doc.py',
    'app/infra/store.py',
    'web/index.html',
    'web/js/app-core.js',
    'web/js/app-contract-status.js',
    'web/js/app-expiry.js',
    'web/js/app-order.js',
    'web/js/app-docx.js',
    'web/js/app-main.js',
    'web/js/system-panel.js',
    'web/contract.html',
    'web/js/contract-page.js',
]

VERSION = '2026-11-13'
