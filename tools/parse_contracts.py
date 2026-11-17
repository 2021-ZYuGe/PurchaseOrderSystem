# -*- coding: utf-8 -*-
"""命令行入口：解析合同文件夹（首次建库用）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain import parser

if __name__ == '__main__':
    parser.main(interactive=True)
