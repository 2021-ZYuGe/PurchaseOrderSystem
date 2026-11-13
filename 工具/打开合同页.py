# -*- coding: utf-8 -*-
"""打开「主合同」页面（新签 / 续签）

不再自己找端口，统一交给 打开系统_静默.py 处理：
  - 本目录的系统在跑 → 直接打开合同页
  - 没在跑 → 先起服务再打开
  - 端口上跑的是旧代码 / 别的文件夹的旧系统 → 先接管，再打开
这样就不会出现"点开合同页，用的却是旧模板、旧数据"。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录

# 被 python.exe 拉起时，直接把自己换成 pythonw 运行（不弹黑窗口）
if sys.executable and os.path.basename(sys.executable).lower() == 'python.exe':
    _pw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if os.path.exists(_pw):
        os.execl(_pw, _pw, os.path.abspath(__file__))


def main():
    exe = os.path.join(ROOT, '运行环境', 'pythonw.exe')
    if not os.path.isfile(exe):
        exe = sys.executable
    script = os.path.join(HERE, '打开系统_静默.py')
    if not os.path.isfile(script):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, '找不到 工具\\打开系统_静默.py，文件夹不完整。', '采购下单系统', 0x10)
        except Exception:
            pass
        return
    subprocess.Popen([exe, script, '--open=/contract.html'], cwd=ROOT)


if __name__ == '__main__':
    main()
