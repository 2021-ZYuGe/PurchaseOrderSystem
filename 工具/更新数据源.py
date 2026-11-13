# -*- coding: utf-8 -*-
"""更新数据源：把新导出的合同文件夹灌进系统（双击即可，不依赖 bat）

用法：双击本文件 → 粘贴（或把文件夹拖进来）合同文件夹路径 → 回车
"""
import os
import shutil
import subprocess
import sys

import sqlite_store

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
GEN = os.path.join(HERE, '_工具_生成数据库.py')
WEB = os.path.join(ROOT, 'web')
DATA = os.path.join(WEB, 'data.js')
LOG = os.path.join(ROOT, 'data', '_更新数据日志.txt')


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time_str(), msg))
    except Exception:
        pass


def ask(prompt):
    """读取一行，无键盘输入环境（被脚本拉起）时返回空字符串"""
    try:
        return input(prompt)
    except EOFError:
        return ''


def pause(msg='按回车关闭…'):
    try:
        input(msg)
    except EOFError:
        pass


def time_str():
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S')


def count_products(path=None):
    """统计 SQLite 正式库中的产品数；保留旧参数以兼容现有调用。"""
    try:
        return sqlite_store.product_count()
    except Exception:
        return 0


def main():
    print()
    print('============================================')
    print('       采购下单系统 · 更新数据源')
    print('============================================')
    print()
    print('  把【企微易快报导出的合同文件夹】路径粘贴到下面，')
    print('  也可以直接把文件夹拖进这个窗口，然后回车。')
    print()

    path = ask('> ').strip().strip('"')
    if not path:
        print('没有输入路径，已取消。')
        return
    if not os.path.isdir(path):
        print('找不到这个文件夹：' + path)
        return

    print()
    print('正在生成数据，请稍候…（合同越多越慢）')
    print()

    # 生成前同时备份 SQLite 主库和旧网页缓存。
    sqlite_store.ensure_database()
    backup = DATA + '.bak'
    db_backup = None
    before = count_products()
    if before:
        db_backup = sqlite_store.backup_database('before_full_update')
        if os.path.exists(DATA):
            shutil.copy2(DATA, backup)
        print('已备份原数据库（原来 %d 个产品）' % before)

    r = subprocess.run([sys.executable, GEN, path])
    log('生成目录 %s -> 返回码 %s' % (path, r.returncode))

    after = count_products(DATA)

    # 安全网：新数据明显比旧数据少，说明很可能指向了"部分合同"文件夹
    if before and after and after < before * 0.6:
        print()
        print('============================================')
        print('  【提醒】新数据比原来少很多：')
        print('    原来 %d 个产品 → 现在只有 %d 个' % (before, after))
        print()
        print('  多半是这次指的文件夹里只有一部分合同。')
        print('  应该指向【完整的合同文件夹】（含所有历史合同）。')
        print('============================================')
        print()
        ans = ask('  要保留这份新数据吗？保留请输入 y 后回车；\n  直接回车则恢复原来的 %d 个产品：\n> ' % before).strip().lower()
        if ans != 'y':
            if db_backup:
                sqlite_store.restore_database(db_backup)
            elif os.path.exists(backup):
                shutil.copy2(backup, DATA)
            log('已回滚到 SQLite 备份（保留 %d 个产品）' % before)
            print()
            print('已恢复原来的数据（%d 个产品）。' % before)
            print('下次请指向完整的合同文件夹。')
            print()
            pause()
            return

    if r.returncode == 0 and after:
        size = os.path.getsize(DATA) / 1024 / 1024
        print()
        print('============================================')
        print('  数据更新完成！%d 个产品 → %d 个产品' % (before or 0, after))
        print('  data.js 大小：%.2f MB' % size)
        print()
        print('  双击桌面【采购下单系统】图标即可使用新数据。')
        print('============================================')
    elif r.returncode == 0 and after == before:
        # 生成器正常结束但未找到可提取产品，原始数据未改动
        print()
        print('============================================')
        print('  数据没有被改动（还是原来 %d 个产品）' % (before or 0))
        print()
        print('  最常见的原因：那个文件夹里没有 .docx 合同文件，')
        print('  或者路径指到了子文件夹。')
        print()
        print('  请换成【包含全部 .docx 合同】的那个文件夹再试。')
        print('============================================')
    else:
        print()
        print('生成没有成功（返回码 %s）。请把「_更新数据日志.txt」发给管理员。' % r.returncode)

    print()
    pause()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('异常: %r' % (e,))
        print('出错了：%s' % e)
        pause()
