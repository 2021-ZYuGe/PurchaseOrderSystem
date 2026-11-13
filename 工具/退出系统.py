# -*- coding: utf-8 -*-
"""退出采购下单系统：把所有在跑的本系统实例都关掉

以前只关找到的第一个端口，结果旧文件夹里的副本还留着，
下次打开网页又跑回旧系统。现在一次关干净。
"""
import ctypes
import io
import os
import sys

# pythonw 下没有控制台，print 会报错，先兜住
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

HERE = os.path.dirname(os.path.abspath(__file__))


def msgbox(text, flag=0x40):
    ctypes.windll.user32.MessageBoxW(0, text, '采购下单系统', flag)


def main():
    sys.path.insert(0, HERE)
    try:
        import 自检与清理 as zj
    except Exception as e:
        msgbox('退出失败：读不到 工具\\自检与清理.py\n%s' % e, 0x10)
        return

    try:
        before = zj.running_ports()
    except Exception as e:
        msgbox('关闭时出错：%s' % e, 0x10)
        return

    if not before:
        msgbox('当前没有在运行中的采购下单系统。')
        return

    try:
        left = zj.stop_all(verbose=False)
    except Exception as e:
        msgbox('关闭时出错：%s' % e, 0x10)
        return

    if left:
        msgbox('有 %d 个实例没关掉（端口 %s）。\n\n'
               '请重启电脑，或双击最新的「采购合同下单系统」图标——'
               '新版启动时会自动停掉旧实例。'
               % (len(left), '、'.join(str(p) for p in left)), 0x30)
    else:
        msgbox('已关闭采购下单系统（共 %d 个实例）。\n'
               '下次双击桌面上的「采购合同下单系统」图标即可。' % len(before))


if __name__ == '__main__':
    main()
