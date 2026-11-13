# -*- coding: utf-8 -*-
"""采购下单系统 · 一键自检与清理

解决的问题：把系统拷到另一台电脑后，说不清跑的是新系统还是旧系统。

用法（双击根目录「一键自检清理.bat」最省事）：
    自检与清理.py               菜单
    自检与清理.py --check       只看信息，不动任何文件
    自检与清理.py --clean       停服务 → 清缓存 → 重建网页缓存 → 重启
    自检与清理.py --clean-all   同上，并删掉 web/_生成合同 里的历史合同
    自检与清理.py --report      只写 自检报告.txt（拿来和另一台电脑对比）
    自检与清理.py --disable-others [--yes]
                                停用本机其它副本：停服务 → 旧文件夹改名 → 重建快捷方式
    加 --no-restart 只清理不重启

只用标准库，不依赖 python-docx。
"""
import hashlib
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))          # 工具/
ROOT = os.path.dirname(HERE)                                # 项目根
PORTS = range(8899, 8931)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 绕开公司代理
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# 决定“合同长什么样”和“程序逻辑”的文件，任何一个不同，指纹就不同
# P1 起真实代码在 app/ 分层目录；工具/ 下只保留兼容入口，不再参与指纹
KEY_FILES = [
    'app/config.py',
    'app/domain/contract_doc.py',
    'app/infra/store.py',
    'app/api/server.py',
    'app/api/routes.py',
    'app/services/contracts.py',
    'app/services/archive.py',
    'app/services/sync.py',
    'web/index.html',
    'web/js/app-core.js',
    'web/js/app-contract-status.js',
    'web/js/app-expiry.js',
    'web/js/app-order.js',
    'web/js/app-docx.js',
    'web/js/app-main.js',
    'web/js/system-panel.js',
    'web/vendor/vue.global.prod.js',
    'web/contract.html',
    'web/js/contract-page.js',
    '合同模板/主合同-一次性发货.docx',
    '合同模板/主合同-一件代发.docx',
    '合同模板/主合同-单次简易版.docx',
]
TPL_FILES = [
    '合同模板/主合同-一次性发货.docx',
    '合同模板/主合同-一件代发.docx',
    '合同模板/主合同-单次简易版.docx',
]

REPORT_NAME = '自检报告.txt'


# ---------------- 小工具 ----------------
def md5_file(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def fingerprint(paths, root=ROOT):
    """把一组文件的路径 + 内容揉成一个 8 位指纹"""
    h = hashlib.md5()
    missing = []
    for rel in paths:
        p = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(p):
            missing.append(rel)
            continue
        h.update(rel.replace('\\', '/').encode('utf-8'))
        h.update(md5_file(p).encode('ascii'))
    return h.hexdigest()[:8].upper(), missing


def size_str(n):
    if n >= 1 << 20:
        return '%.1f MB' % (n / float(1 << 20))
    if n >= 1 << 10:
        return '%.0f KB' % (n / float(1 << 10))
    return '%d B' % n


def mtime_str(path):
    try:
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(path)))
    except Exception:
        return '—'


def dwidth(s):
    """中文字符占两格，用来对齐表格"""
    return sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in str(s))


def pad(s, width):
    s = str(s)
    return s + ' ' * max(0, width - dwidth(s))


def run_cmd(args, timeout=8):
    """静默执行系统命令，返回文本"""
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW)
        return (p.stdout or b'').decode('mbcs', 'replace')
    except Exception:
        return ''


def tcp_snapshot():
    """一次 netstat 拿到所有监听端口 -> PID，比逐个端口试探快 10 倍"""
    txt = run_cmd(['netstat', '-ano', '-p', 'tcp'])
    out = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[3].upper() == 'LISTENING':
            try:
                port = int(parts[1].rsplit(':', 1)[-1])
            except Exception:
                continue
            out.setdefault(port, set()).add(parts[4])
    return out


def port_open(port, snapshot=None):
    snap = snapshot if snapshot is not None else tcp_snapshot()
    return port in snap


def is_our_server(port):
    """只认正式服务的 /__ping，静态预览服务不算"""
    try:
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return False
    except Exception:
        return False
    try:
        r = OPENER.open('http://127.0.0.1:%d/__ping' % port, timeout=1.5)
        if r.status != 200:
            return False
        # 新版返回 pong|目录|版本，旧版只返回 pong，都要认
        return r.read().split(b'|')[0].strip() == b'pong'
    except Exception:
        return False


def running_ports(snapshot=None):
    snap = snapshot if snapshot is not None else tcp_snapshot()
    return [p for p in PORTS if p in snap and is_our_server(p)]


def pid_image(pid):
    txt = run_cmd(['tasklist', '/FI', 'PID eq %s' % pid, '/FO', 'CSV', '/NH'])
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith('"'):
            return line.split('","')[0].strip('"')
    return ''


def ensure_docx_free_stdout():
    """被 bat 重定向时避免编码报错"""
    try:
        if sys.stdout and not sys.stdout.isatty():
            sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass


# ---------------- 停 / 起 ----------------
def stop_all(verbose=True):
    """停掉所有在跑的系统实例（包括开机自启留下来的）"""
    snap = tcp_snapshot()
    ports = running_ports(snap)
    if not ports:
        if verbose:
            line('服务当前没有运行。')
        return []

    if verbose:
        line('发现正在运行的系统：端口 %s' % ', '.join(str(p) for p in ports))
    for p in ports:
        try:
            OPENER.open('http://127.0.0.1:%d/__stop' % p, timeout=2).read()
        except Exception:
            pass

    deadline = time.time() + 6
    while time.time() < deadline and running_ports():
        time.sleep(0.3)

    left = running_ports()
    if not left:
        if verbose:
            line('已正常关闭。')
        return []

    # 优雅关闭失败：只对 python/pythonw 进程强制结束，别的程序绝不碰
    if verbose:
        line('有实例没响应关闭指令，尝试强制结束 …')
    snap = tcp_snapshot()
    for p in left:
        for pid in snap.get(p, set()):
            image = pid_image(pid).lower()
            if 'python' in image:
                run_cmd(['taskkill', '/PID', pid, '/F'])
                if verbose:
                    line('  已结束 %s (PID %s, 端口 %d)' % (image or '进程', pid, p))
            elif verbose:
                line('  端口 %d 被 %s (PID %s) 占用，不是本系统，跳过' % (p, image or '未知程序', pid))

    time.sleep(1.0)
    return running_ports()


def start_server():
    """后台拉起服务（和双击快捷方式的效果一致）"""
    exe = os.path.join(ROOT, '运行环境', 'pythonw.exe')
    if not os.path.isfile(exe):
        exe = sys.executable
    script = os.path.join(HERE, '打开系统_静默.py')
    if not os.path.isfile(script):
        return None, '找不到 工具\\打开系统_静默.py'
    try:
        subprocess.Popen([exe, script], cwd=ROOT, close_fds=True,
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
    except Exception as e:
        return None, str(e)
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.4)
        ports = running_ports()
        if ports:
            return ports[0], None
    return None, '起了但 15 秒内没响应（看 data/_运行日志.txt 最后几行）'


# ---------------- 清缓存 ----------------
def remove_pycache():
    """删掉 __pycache__：排除 运行环境，免得动到 Python 本体"""
    removed = []
    for dirpath, dirnames, _ in os.walk(ROOT):
        parts = dirpath.split(os.sep)
        if '运行环境' in parts:
            dirnames[:] = []
            continue
        for name in list(dirnames):
            if name == '__pycache__':
                target = os.path.join(dirpath, name)
                shutil.rmtree(target, ignore_errors=True)
                removed.append(os.path.relpath(target, ROOT))
                dirnames.remove(name)
    return removed


def rebuild_cache():
    """P2 起页面实时查库，不再生成 web/data.js；这里改为校验数据库并返回统计。"""
    sys.path.insert(0, HERE)
    try:
        import sqlite_store
    finally:
        if sys.path and sys.path[0] == HERE:
            sys.path.pop(0)
    try:
        sqlite_store.verify_database()
        counts = sqlite_store.database_counts()
        return (counts.get('products', 0), counts.get('suppliers', 0),
                sqlite_store.database_stamp())
    except Exception as e:
        return None, None, str(e)


def drop_folder_icon(verbose=True):
    """清掉旧版留下的 desktop.ini 与目录系统属性（新版已不写，见 _创建快捷方式.py）

    本来干净时不做任何写操作；返回 restore_folder_appearance() 的状态或 None。
    """
    sys.path.insert(0, HERE)
    try:
        import _创建快捷方式
    except Exception as e:
        if verbose:
            line('文件夹外观检查跳过：%s' % e)
        return None
    finally:
        if sys.path and sys.path[0] == HERE:
            sys.path.pop(0)

    try:
        st = _创建快捷方式.restore_folder_appearance()
    except Exception as e:
        if verbose:
            line('文件夹外观清理失败：%s' % e)
        return None

    if verbose:
        if st == 'removed':
            line('已删除旧版留下的 desktop.ini（文件夹恢复默认外观）')
        elif st == 'cleaned':
            line('已摘掉目录的系统属性（文件夹恢复默认外观）')
        elif st == 'failed':
            line('desktop.ini 删不掉，可能被资源管理器占用，重启后再跑一次')
    return st


def generated_contracts():
    gen = os.path.join(ROOT, 'web', '_生成合同')
    if not os.path.isdir(gen):
        return []
    return [f for f in os.listdir(gen) if f.lower().endswith('.docx')]


def clean(remove_contracts=False, restart=True, verbose=True):
    line('=' * 56)
    line('  清理开始')
    line('=' * 56)

    left = stop_all(verbose=verbose)
    if left:
        line('警告：端口 %s 仍被占用，缓存可能删不掉。' % ', '.join(str(p) for p in left))

    drop_folder_icon(verbose=verbose)

    removed = remove_pycache()
    if verbose:
        line('已清除 Python 字节码缓存：%d 处' % len(removed))

    products, suppliers, stamp = rebuild_cache()
    if products is None:
        line('重建网页缓存失败：%s' % stamp)
    elif verbose:
        line('已从数据库重建网页缓存：产品 %s 个，供应商 %s 家，指纹 %s'
             % (products, suppliers, stamp))

    if remove_contracts:
        files = generated_contracts()
        gen = os.path.join(ROOT, 'web', '_生成合同')
        for f in files:
            try:
                os.remove(os.path.join(gen, f))
            except Exception:
                pass
        if verbose:
            line('已删除历史生成的合同：%d 份' % len(files))

    if restart:
        port, err = start_server()
        if port:
            line('系统已重新启动：http://127.0.0.1:%d/index.html' % port)
        else:
            line('重启失败：%s' % err)
            line('可以手动双击「启动网页版.bat」再试。')
    line('')


# ---------------- 自检 ----------------
FONTS = [
    ('仿宋', 'simfang.ttf', True),
    ('宋体 / 新宋体', 'simsun.ttc', True),
    ('黑体', 'simhei.ttf', False),
    ('微软雅黑', 'msyh.ttc', False),
]


def font_installed(filename):
    bases = [
        os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
    ]
    return any(os.path.isfile(os.path.join(b, filename)) for b in bases if b)


def media_info():
    """图片现状：P2 起在 data/media，老版本在 web/图片"""
    for folder in (os.path.join(ROOT, 'data', 'media'), os.path.join(ROOT, 'web', '图片')):
        if not os.path.isdir(folder):
            continue
        count = size = 0
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                count += 1
                size += os.path.getsize(p)
        return {'dir': os.path.relpath(folder, ROOT), 'count': count, 'size': size}
    return None


SKIP_DIRS = {
    '运行环境', '$RECYCLE.BIN', 'System Volume Information', 'Windows',
    'Program Files', 'Program Files (x86)', 'ProgramData', 'AppData',
    'node_modules', '.git', 'Recovery', 'PerfLogs', '$WinREAgent', '.workbuddy',
}


def find_other_copies(deadline_seconds=6.0):
    """在桌面 / 下载 / 文档 / 各盘根目录里找别的系统副本"""
    home = os.path.expanduser('~')
    starts = []
    for name in ('Desktop', 'OneDrive/Desktop', 'Downloads', 'Documents'):
        p = os.path.join(home, name.replace('/', os.sep))
        if os.path.isdir(p):
            starts.append(p)
    if os.name == 'nt':
        for letter in 'CDEFGH':
            drive = letter + ':\\'
            if os.path.isdir(drive):
                starts.append(drive)

    deadline = time.time() + deadline_seconds
    found = []
    seen = set()

    def scan(base, depth):
        if time.time() > deadline or len(found) > 8:
            return
        try:
            entries = list(os.scandir(base))
        except Exception:
            return
        for e in entries:
            if time.time() > deadline or len(found) > 8:
                return
            try:
                if not e.is_dir(follow_symlinks=False):
                    continue
            except Exception:
                continue
            if e.name in SKIP_DIRS or e.name.startswith('.'):
                continue
            if '旧版停用' in e.name:
                continue                      # 已经停用过的副本，不用再列
            marker = os.path.join(e.path, '工具', '打开系统_静默.py')
            if os.path.isfile(marker):
                real = os.path.normcase(os.path.abspath(e.path))
                if real != os.path.normcase(ROOT) and real not in seen:
                    seen.add(real)
                    fp, missing = fingerprint(KEY_FILES, root=e.path)
                    runnable = (os.path.isfile(os.path.join(e.path, '启动网页版.bat'))
                                or os.path.isfile(os.path.join(e.path, '运行环境', 'python.exe')))
                    found.append({'path': e.path,
                                  'fp': fp if not missing else '—',
                                  'missing': len(missing),
                                  'runnable': runnable,
                                  'mtime': mtime_str(marker)})
                continue
            if depth > 1:
                scan(e.path, depth - 1)

    for s in starts:
        depth = 3 if os.path.normcase(s).startswith(os.path.normcase(home)) else 2
        scan(s, depth)
    return found


def shortcut_info():
    """读桌面快捷方式到底指向哪个文件夹"""
    home = os.path.expanduser('~')
    lnks = [os.path.join(home, 'Desktop', '采购合同下单系统.lnk'),
            os.path.join(home, 'OneDrive', 'Desktop', '采购合同下单系统.lnk'),
            os.path.join(ROOT, '采购合同下单系统.lnk')]
    for lnk in lnks:
        if not os.path.isfile(lnk):
            continue
        ps = ('$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\'%s\');'
              'Write-Output $s.TargetPath;Write-Output $s.WorkingDirectory' % lnk)
        txt = run_cmd(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], timeout=10)
        lines = [x.strip() for x in txt.splitlines() if x.strip()]
        if lines:
            return {'lnk': lnk, 'target': lines[0],
                    'workdir': lines[1] if len(lines) > 1 else ''}
    return None


# ---------------- 停用其它副本（换电脑后"新旧系统混着跑"的解药） ----------------
def _unique_dest(parent, base, stamp):
    dest = os.path.join(parent, '%s_旧版停用_%s' % (base, stamp))
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(parent, '%s_旧版停用_%s_%d' % (base, stamp, n))
        n += 1
    return dest


def rename_copy_folder(path):
    """把旧副本文件夹改名（不删任何文件，改回原名即可恢复）"""
    path = os.path.abspath(str(path).rstrip('\\/'))
    parent, base = os.path.split(path)
    dest = _unique_dest(parent, base, time.strftime('%Y%m%d'))
    os.rename(path, dest)
    return dest


def rebuild_shortcut():
    """按当前目录重建快捷方式（内容不变，只是重新指向本目录）"""
    exe = os.path.join(ROOT, '运行环境', 'python.exe')
    if not os.path.isfile(exe):
        exe = sys.executable
    script = os.path.join(HERE, '_创建快捷方式.py')
    if not os.path.isfile(script):
        return False, '找不到 工具\\_创建快捷方式.py'
    try:
        p = subprocess.run([exe, script], cwd=ROOT, capture_output=True,
                           timeout=40, creationflags=CREATE_NO_WINDOW)
        txt = (p.stdout or b'').decode('mbcs', 'replace').strip()
        return p.returncode == 0, txt
    except Exception as e:
        return False, str(e)


def _confirm(text):
    try:
        return input(text).strip()
    except (EOFError, KeyboardInterrupt):
        return ''


def disable_other_copies(assume_yes=False, interactive=True, verbose=True):
    """停用本机其它系统副本：停服务 → 旧文件夹改名 → 重建快捷方式 → 重启当前系统"""
    line('=' * 56)
    line('  停用本机其它系统副本（旧系统）')
    line('=' * 56)

    copies = find_other_copies()
    if not copies:
        line('没有在桌面 / 下载 / 文档 / 各盘根目录发现其它副本。')
        if interactive and not assume_yes:
            p = _confirm('如果旧系统在别的目录，可粘贴完整路径（直接回车退出）：').strip('"').strip()
            if not p:
                return
            marker = os.path.join(p, '工具', '打开系统_静默.py')
            if not os.path.isfile(marker):
                line('这个目录里没有本系统的启动脚本，先确认路径对不对：%s' % p)
                return
            fp, missing = fingerprint(KEY_FILES, root=p)
            copies = [{'path': os.path.abspath(p), 'fp': fp if not missing else '—',
                       'missing': len(missing), 'runnable': True,
                       'mtime': mtime_str(marker)}]
        else:
            return

    live = [c for c in copies if c.get('runnable')]
    idle = [c for c in copies if not c.get('runnable')]

    sys_fp, _ = fingerprint(KEY_FILES)
    line('')
    line('当前这份：%s' % ROOT)
    line('    指纹 %s' % sys_fp)

    if idle:
        line('')
        line('另有 %d 个不完整的旧包（没有启动文件/运行环境，打不开，不用管）：' % len(idle))
        for c in idle:
            line('    %s' % c['path'])

    if not live:
        line('')
        line('没有发现能独立运行的其它副本，不需要停用。')
        return

    line('')
    line('发现 %d 个能独立运行的其它副本：' % len(live))
    for i, c in enumerate(live, 1):
        if c['fp'] == sys_fp:
            tag = '（和当前版本相同，只是另一份拷贝）'
        elif c['missing']:
            tag = '（文件不全）'
        else:
            tag = '（另一个版本，很可能是旧系统）'
        line('  %d. %s' % (i, c['path']))
        line('     指纹 %s    程序修改时间 %s    %s' % (c['fp'], c['mtime'], tag))

    line('')
    line('!! 接下来会做的事（不删除任何文件）：')
    line('   1) 停掉所有正在运行的系统实例（包括旧副本的）')
    line('   2) 把上面这些文件夹改名，末尾加「_旧版停用_日期」')
    line('      数据和已生成的合同都还在里面，改回原名就能恢复')
    line('   3) 重建当前这份系统的快捷方式，然后重新启动当前系统')
    line('')

    if not assume_yes:
        if not interactive:
            line('没加 --yes，已取消（什么都没改）。')
            return
        line('⚠️ 此操作会改名上述文件夹。内容不删，但请先确认没有别的程序在用它们。')
        if _confirm('确认请输入「停用」两个字：') != '停用':
            line('已取消，什么都没有改。')
            return

    left = stop_all(verbose=verbose)
    if left:
        line('提示：端口 %s 没停掉，改名可能失败。' % ', '.join(str(p) for p in left))

    renamed, failed = [], []
    for c in live[:10]:
        try:
            dest = rename_copy_folder(c['path'])
            renamed.append((c['path'], dest))
            if verbose:
                line('已改名：%s' % dest)
        except Exception as e:
            failed.append((c['path'], str(e)))
            line('改名失败：%s（%s）' % (c['path'], e))

    line('')
    ok, out = rebuild_shortcut()
    lnk = os.path.join(ROOT, '采购合同下单系统.lnk')
    if ok:
        line('快捷方式已重新指向当前目录：%s' % lnk)
        line('  → 如果桌面上还有旧的「采购合同下单系统」图标，把它删掉，')
        line('    再把这个 .lnk 拖到桌面即可。')
    else:
        line('快捷方式重建失败：%s' % (out[-200:] or '未知错误'))

    if renamed or failed:
        line('')
        line('处理结果：成功 %d 个，失败 %d 个。' % (len(renamed), len(failed)))
        for old, new in renamed:
            line('  原名：%s' % old)
            line('  现名：%s' % new)
        if failed:
            line('  失败的可以直接关掉占用它的程序后再跑一次本功能。')

    port, err = start_server()
    if port:
        line('')
        line('当前系统已重新启动：http://127.0.0.1:%d/index.html' % port)
        if not interactive:
            line('（浏览器没有自动打开时，手动访问上面的地址即可）')
    else:
        line('')
        line('重启失败：%s' % err)
        line('可以双击根目录的「启动网页版.bat」再试。')


def autostart_entries():
    """开机自启里有没有挂本系统"""
    home = os.path.expanduser('~')
    dirs = [os.path.join(home, 'AppData', 'Roaming', 'Microsoft', 'Windows',
                         'Start Menu', 'Programs', 'Startup'),
            os.path.join(os.environ.get('ProgramData', r'C:\ProgramData'),
                         'Microsoft', 'Windows', 'Start Menu', 'Programs', 'StartUp')]
    hits = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            low = name.lower()
            if '开机自启' in name or '采购' in name or low.endswith('.pyw'):
                hits.append(os.path.join(d, name))
    return hits


def log_tail(n=6):
    p = os.path.join(ROOT, 'data', '_运行日志.txt')
    if not os.path.isfile(p):
        return []
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except Exception:
        return []


def build_report():
    L = []

    def add(s=''):
        L.append(s)

    sys_fp, sys_missing = fingerprint(KEY_FILES)
    tpl_fp, tpl_missing = fingerprint(TPL_FILES)
    snap = tcp_snapshot()
    ports = running_ports(snap)
    mi = media_info()
    db = os.path.join(ROOT, 'data', 'purchase.db')
    pycache = []
    for dirpath, dirnames, _ in os.walk(ROOT):
        if '运行环境' in dirpath.split(os.sep):
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) == '__pycache__':
            pycache.append(dirpath)

    add('采购下单系统 · 自检报告')
    add('生成时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    add('计算机名：%s    用户：%s' % (os.environ.get('COMPUTERNAME', '—'),
                                      os.environ.get('USERNAME', '—')))
    add('系统目录：%s' % ROOT)
    add('操作系统：%s' % platform.platform())
    add('')
    add('[1] 版本指纹（两台电脑对比这一个数就够了）')
    add('    系统指纹：%s    ← 程序 + 合同模板' % sys_fp)
    add('    模板指纹：%s    ← 只算三份模板' % tpl_fp)
    if sys_missing:
        add('    !! 缺少关键文件：%s' % '、'.join(sys_missing))
    if tpl_missing:
        add('    !! 缺少合同模板：%s' % '、'.join(tpl_missing))
    add('')
    add('[2] 关键文件')
    for rel in KEY_FILES:
        p = os.path.join(ROOT, rel.replace('/', os.sep))
        if os.path.isfile(p):
            add('    %s%s  %s  %s' % (pad(rel, 36), pad(size_str(os.path.getsize(p)), 9),
                                      mtime_str(p), md5_file(p)[:8].upper()))
        else:
            add('    %s%s' % (pad(rel, 36), '缺失'))
    add('')
    add('[3] 运行状态')
    if ports:
        add('    正在运行：端口 %s' % ', '.join(str(p) for p in ports))
        add('    页面地址：http://127.0.0.1:%d/index.html' % ports[0])
    else:
        add('    当前没有运行')
    for p in range(8899, 8931):
        if p in snap and p not in ports:
            pids = snap.get(p, set())
            add('    注意：端口 %d 被别的程序占用（PID %s），会让系统起不来'
                % (p, ', '.join(pids) if pids else '未知'))
    auto = autostart_entries()
    if auto:
        add('    开机自启：%s' % '；'.join(os.path.basename(a) for a in auto))
        add('              （开机就拉起旧实例时，双击新快捷方式也会连到旧系统）')
    else:
        add('    开机自启：未发现')
    add('')
    add('[4] 图片与数据')
    if mi:
        add('    %-16s %d 张  %.1f MB' % (mi['dir'], mi['count'], mi['size'] / 1024 / 1024))
    else:
        add('    图片目录         不存在（首次导入合同时自动创建）')
    if os.path.isfile(db):
        add('    data/purchase.db %s  %s' % (size_str(os.path.getsize(db)), mtime_str(db)))
    else:
        add('    data/purchase.db 不存在')
    add('    __pycache__      %d 处' % len(pycache))
    add('')
    add('[5] 字体（模板正文是仿宋，缺了会被替换成别的字体）')
    for label, fn, must in FONTS:
        ok = font_installed(fn)
        add('    %s%s%s' % (pad(label, 16), '已安装' if ok else '缺失',
                            '' if ok or not must else '   ← 必须补装'))
    add('')
    add('[6] 本机其它系统副本')
    copies = find_other_copies()
    if copies:
        for c in copies:
            add('    %s' % c['path'])
            tag = ''
            if not c.get('runnable'):
                tag = '    （不完整，不能独立运行，可忽略）'
            elif c['missing']:
                tag = '    （文件不全）'
            elif c['fp'] != sys_fp:
                tag = '    ← 指纹和当前这份不同，是另一个版本'
            add('        指纹 %s    程序修改时间 %s%s' % (c['fp'], c['mtime'], tag))
    else:
        add('    未发现其它副本')
    sc = shortcut_info()
    if sc:
        same = os.path.normcase(os.path.abspath(sc['workdir'] or '')) == os.path.normcase(ROOT)
        add('')
        add('[7] 桌面快捷方式')
        add('    %s' % sc['lnk'])
        add('    目标程序：%s' % (sc['target'] or '—'))
        add('    工作目录：%s' % (sc['workdir'] or '—'))
        if not same:
            add('    !! 快捷方式指的不是当前这份系统，双击会跑到别处')
    tail = log_tail()
    if tail:
        add('')
        add('[8] 运行日志最后几行')
        for ln in tail:
            add('    ' + ln)
    return L


def line(s=''):
    print(s)


def show_report(write_file=False):
    L = build_report()
    for s in L:
        line(s)
    if write_file:
        path = os.path.join(ROOT, REPORT_NAME)
        try:
            with open(path, 'w', encoding='utf-8-sig') as f:
                f.write('\n'.join(L) + '\n')
            line('')
            line('报告已保存：%s' % path)
            line('（把这个文件发给我，或者和另一台电脑的报告对比「系统指纹」即可）')
        except Exception as e:
            line('报告写入失败：%s' % e)
    return L


# ---------------- 菜单 ----------------
MENU = """
============================================================
  采购下单系统 · 自检与清理
============================================================
  1  查看自检信息（不动任何文件）
  2  清缓存并重启（推荐：换电脑/换版本后用这个）
  3  清缓存 + 删除已生成的旧合同 + 重启
  4  生成「自检报告.txt」（发给另一台电脑对比）
  5  停用本机其它副本（旧系统）：停服务 → 旧文件夹改名 → 重建快捷方式
  0  退出
------------------------------------------------------------
"""


def menu():
    while True:
        print(MENU)
        try:
            choice = input('请输入数字后回车：').strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice == '0':
            return
        if choice == '1':
            print()
            show_report(write_file=False)
            print()
        elif choice == '2':
            clean(remove_contracts=False, restart=True)
            show_report(write_file=False)
        elif choice == '3':
            n = len(generated_contracts())
            print()
            print('web/_生成合同 里有 %d 份已生成的合同，删除后不可恢复。' % n)
            try:
                ok = input('确定删除？(y/N) ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                ok = ''
            clean(remove_contracts=(ok == 'y'), restart=True)
            show_report(write_file=False)
        elif choice == '4':
            print()
            show_report(write_file=True)
            print()
        elif choice == '5':
            print()
            disable_other_copies(interactive=True)
            print()
        else:
            print('请输入 0-5。')


def main():
    ensure_docx_free_stdout()
    args = [a.lower() for a in sys.argv[1:]]
    no_restart = '--no-restart' in args

    if '--check' in args:
        show_report(write_file=False)
    elif '--report' in args:
        show_report(write_file=True)
    elif '--clean' in args or '--clean-all' in args:
        clean(remove_contracts=('--clean-all' in args), restart=not no_restart)
        show_report(write_file=False)
    elif '--disable-others' in args:
        disable_other_copies(assume_yes=('--yes' in args), interactive=('--yes' not in args))
    else:
        menu()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
