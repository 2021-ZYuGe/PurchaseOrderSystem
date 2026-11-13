# -*- coding: utf-8 -*-
"""同事端一键入口：双击即可

特点：
  1. 无论你把它关联到 python.exe 还是 pythonw.exe，都会自动用【无黑窗口】方式运行
  2. 已经在运行时不会重复启动，直接打开浏览器
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(ROOT, '打开系统_静默.py')

if not os.path.isfile(TARGET):
    TARGET = os.path.join(ROOT, '启动采购下单系统.py')

EXE = sys.executable or ''
BASE = os.path.basename(EXE).lower()

# 当前用的是带控制台的解释器 → 换成同目录的 pythonw.exe，运行起来没有黑窗口
if BASE.startswith('python') and not BASE.startswith('pythonw'):
    candidate = os.path.join(os.path.dirname(EXE), 'pythonw.exe')
    if os.path.isfile(candidate):
        EXE = candidate

os.execl(EXE, EXE, '"%s"' % TARGET)
