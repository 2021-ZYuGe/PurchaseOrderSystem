# -*- coding: utf-8 -*-
"""命令行入口：把一批新合同合并进现有库。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain import merge

if __name__ == '__main__':
    merge.main()
