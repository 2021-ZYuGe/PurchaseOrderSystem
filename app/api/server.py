# -*- coding: utf-8 -*-
"""采购下单系统 · 本地 HTTP 服务（api 层）

只保留三件事：
  1. 接静态页面和 /api/* 请求（路由表在 routes.py）
  2. 单实例、端口、浏览器、关页面自动退出的生命周期
  3. 页面在线状态（SSE）

业务逻辑不要写在这里。
"""
import functools
import hashlib
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

import app.config as config
from app.api import routes
from app.infra import media, store as sqlite_store
from app.infra.logging import log
from app.services import archive as archive_service
from app.services import backup as backup_service
from app.services import setup as setup_service

HERE = os.path.dirname(os.path.abspath(__file__))      # app/api
ROOT = config.ROOT                                      # 项目根目录
WEB = str(config.WEB_DIR)
# 只起服务、不弹网页（开机自启用）：命令行带 --no-browser 或设环境变量
NO_BROWSER = ('--no-browser' in sys.argv) or (os.environ.get('CAIGOU_NO_BROWSER') == '1')
# 打开哪个页面：默认首页；「打开合同页」会传 --open=/contract.html
OPEN_PATH = '/index.html'
for _a in sys.argv[1:]:
    if _a.startswith('--open='):
        OPEN_PATH = _a.split('=', 1)[1] or OPEN_PATH
        if not OPEN_PATH.startswith('/'):
            OPEN_PATH = '/' + OPEN_PATH
PORT_FROM, PORT_TO = 8899, 8930
LOG = str(config.LOG_PATH)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
APP_VER = config.VERSION      # 版本日期：页面右上角会显示，用来一眼区分新旧系统
CREATE_NO_WINDOW = 0x08000000
# 想故意同时开两份（调试用）时，设环境变量 CAIGOU_ALLOW_MULTI=1
# 正式分发默认单实例：后双击的那份会接管端口，避免旧文件夹的实例继续被打开。
ALLOW_MULTI = os.environ.get('CAIGOU_ALLOW_MULTI') == '1'

STAMP_FILES = config.STAMP_FILES


def build_stamp():
    h = hashlib.md5()
    for rel in STAMP_FILES:
        p = os.path.join(ROOT, rel.replace('/', os.sep))
        try:
            st = os.stat(p)
            h.update(('%s|%d|%d' % (rel, st.st_size, int(st.st_mtime))).encode('utf-8'))
        except Exception:
            h.update(rel.encode('utf-8'))
    return h.hexdigest()[:8].upper()


APP_ID = build_stamp()

STOP = threading.Event()

# ---------------- 页面在线跟踪：关掉网页就自动退出 ----------------
# 页面里的 _alive.js 会开一条 SSE 长连接，连接一断就说明这个页面被关了。
# 所有页面都关掉后，再等 AUTO_STOP_GRACE 秒（留给 F5 刷新重连），确认没页面才退出。
AUTO_STOP_GRACE = 10.0
MAX_ALIVE = 3                      # 最多跟踪 3 个页面，避免占满浏览器 6 个并发连接
AUTO_STOP = not NO_BROWSER         # 开机自启的常驻实例不自动退出

_alive = {}                        # 页面 id -> 最后在线时间
_alive_lock = threading.Lock()
_alive_seen = False                # 是否曾有页面连进来（从没连过就永不退出）
_alive_armed = AUTO_STOP           # 是否允许"关网页就退出"
_alive_empty_at = None             # 从什么时候起没有页面了



def _norm_root(p):
    """路径归一：Windows 不区分大小写，比较项目根目录用"""
    return os.path.normcase(os.path.normpath(str(p or '')))


def _port_open(p):
    try:
        with socket.socket() as s:
            s.settimeout(0.08)
            return s.connect_ex(('127.0.0.1', p)) == 0
    except Exception:
        return False


def scan_instances():
    """扫描端口范围，返回本系统的实例列表 [(端口, 系统目录, 版本, 指纹)]

    先用 socket 毫秒级探活，只有端口真的开着才发 HTTP 请求。
    返回体形如 b'pong|C:\\...\\项目根|2026-11-10|A1B2C3D4'：
      - 第一段必须是 pong（静态预览服务、别的软件会被排除）
      - 后面依次是系统目录、版本、程序指纹；旧版只有前面一两部分
    """
    out = []
    for p in range(PORT_FROM, PORT_TO + 1):
        if not _port_open(p):
            continue
        try:
            r = OPENER.open('http://127.0.0.1:%d/__ping' % p, timeout=1.5)
            if r.status != 200:
                continue
            parts = r.read().decode('utf-8', 'replace').split('|')
            if parts[0].strip() != 'pong':
                continue
            out.append((p,
                        parts[1].strip() if len(parts) > 1 else '',
                        parts[2].strip() if len(parts) > 2 else '',
                        parts[3].strip() if len(parts) > 3 else ''))
        except Exception:
            continue
    return out


def already_running():
    """本目录、且代码版本一致的实例所在端口；没有则返回 None

    只认版本和指纹都相同的：替换过程序文件但旧进程没退时，端口上还是旧代码，
    直接复用会看到"页面功能对不上、数据也不对"的怪现象。
    """
    me = _norm_root(ROOT)
    for p, root, ver, ident in scan_instances():
        if _norm_root(root) == me and ver == APP_VER and ident == APP_ID:
            return p
    return None


def _pid_on_port(port):
    """监听该端口的进程 PID（拿不到返回空串）"""
    try:
        out = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True,
                             timeout=8, creationflags=CREATE_NO_WINDOW).stdout
        txt = out.decode('mbcs', 'replace')
    except Exception:
        return ''
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[3].upper() == 'LISTENING':
            if parts[1].endswith(':%d' % port):
                return parts[4]
    return ''


def _stop_instance(port):
    """先礼后兵：请它自己退出，赖着不走才结束进程（只动 python*.exe）"""
    try:
        OPENER.open('http://127.0.0.1:%d/__stop' % port, timeout=2).read()
    except Exception:
        pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _port_open(port):
            return True
        time.sleep(0.25)

    pid = _pid_on_port(port)
    if not pid:
        return not _port_open(port)
    image = ''
    try:
        out = subprocess.run(['tasklist', '/FI', 'PID eq %s' % pid, '/FO', 'CSV', '/NH'],
                             capture_output=True, timeout=8,
                             creationflags=CREATE_NO_WINDOW).stdout.decode('mbcs', 'replace')
        head = out.strip().splitlines()[0] if out.strip() else ''
        image = head.split('","')[0].strip('"').lower()
    except Exception:
        pass
    if 'python' not in image:
        log('端口 %d 被 %s (PID %s) 占用，不是本系统，不能强杀' % (port, image or '未知程序', pid))
        return False
    try:
        subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True,
                       timeout=8, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    time.sleep(0.8)
    return not _port_open(port)


def take_over_others():
    """把别的目录（旧系统）的实例停掉，保证一台电脑只跑当前这一份

    换电脑时最常见的情况：旧文件夹没删，旧系统还在 8899 上跑着。
    以前的做法是"发现不是本目录就另开一个端口"，结果两份同时在跑，
    浏览器收藏、旧快捷方式、旧标签页随时会把人带回旧系统。
    现在改成：谁最后被双击，谁就接管 8899，其余实例全部停掉。
    """
    if ALLOW_MULTI:
        return []
    me = _norm_root(ROOT)
    stopped = []
    for p, root, ver, ident in scan_instances():
        same = _norm_root(root) == me
        if same and ver == APP_VER and ident == APP_ID:
            continue
        if same:
            log('端口 %d 上跑的是同目录的旧代码（版本 %s/%s），重启成 %s/%s'
                % (p, ver or '未知', ident or '未知', APP_VER, APP_ID))
        else:
            log('发现其它目录的实例：端口 %d，目录 %s，版本 %s，准备停掉'
                % (p, root or '（未上报，可能是旧版）', ver or '（旧版）'))
        if _stop_instance(p):
            stopped.append((p, root or '旧版本（未上报目录）'))
            log('已停掉端口 %d 上的旧实例' % p)
        else:
            log('端口 %d 上的旧实例没停掉，稍后另开端口' % p)
    return stopped


def find_port():
    for p in range(PORT_FROM, PORT_TO + 1):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return None


def open_in_browser(port, path=None):
    """关键：URL 带时间戳，避免浏览器复用同网址的旧标签页（不刷新）"""
    if NO_BROWSER:
        log('本次设定：不自动打开浏览器')
        return ''
    target = path or OPEN_PATH
    url = 'http://127.0.0.1:%d%s?t=%d' % (port, target, int(time.time() * 1000))
    try:
        webbrowser.open(url)
    except Exception as e:
        log('打开浏览器失败: %r' % (e,))
    return url


class Handler(http.server.SimpleHTTPRequestHandler):
    """禁止缓存 + 页面在线状态 + /__ping 等内部指令；/api/* 交给 routes"""

    # ---------- 页面在线状态（关掉网页自动退出用的） ----------
    def _query(self):
        return self.path.split('?', 1)[1] if '?' in self.path else ''

    def _empty_reply(self, code):
        self.send_response(code)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _client_bye(self, qs):
        """页面关闭时的告别通知（尽力而为，SSE 断开才是主判据）"""
        cid = (urllib.parse.parse_qs(qs).get('id') or [''])[0][:64]
        if cid:
            with _alive_lock:
                _alive.pop(cid, None)
        self._empty_reply(204)

    def _sse_alive(self, qs):
        """页面长连接：连接断了就说明这个页面被关掉了"""
        global _alive_seen
        cid = (urllib.parse.parse_qs(qs).get('id') or [''])[0][:64]
        if not cid:
            self._empty_reply(204)
            return
        with _alive_lock:
            if cid not in _alive and len(_alive) >= MAX_ALIVE:
                self._empty_reply(204)     # 页面开太多，这一个不参与计数
                return
            _alive[cid] = time.time()
            _alive_seen = True
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            self.wfile.write(b'retry: 1500\n\n')
            self.wfile.flush()
            while not STOP.is_set():
                if STOP.wait(2.5):
                    break
                self.wfile.write(b': on\n\n')      # 页面关掉后这里会断开报错
                self.wfile.flush()
                with _alive_lock:
                    _alive[cid] = time.time()
        except Exception as e:
            log('页面连接结束(%s): %r' % (cid, e))
        finally:
            with _alive_lock:
                _alive.pop(cid, None)
            self.close_connection = True

    def _serve_media(self, head):
        """产品图片从 data/media 提供；老的 /图片/ 路径继续可用"""
        name = urllib.parse.unquote(head.split('/', 2)[-1])
        path = media.resolve(name)
        if not path:
            self.send_error(404)
            return
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', media.content_type(path))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = self.path.split('?')[0]
        if path in ('/__bye', '/__bye/'):
            # sendBeacon 发的“页面已关闭”通知，body 一般是空的，读掉避免污染连接
            try:
                n = int(self.headers.get('Content-Length') or 0)
                if n:
                    self.rfile.read(n)
            except Exception:
                pass
            self._client_bye(self._query())
            return
        if path == '/api/setup/restore':
            # 原始二进制上传（浏览器直接 POST 文件内容），不走 JSON
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0:
                result = {'ok': False, 'error': '没有收到文件'}
            elif n > setup_service.MAX_RESTORE_BYTES:
                result = {'ok': False, 'error': '数据库文件太大（超过 60MB）'}
            else:
                result = setup_service.restore_database(self.rfile.read(n))
            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not path.startswith('/api/'):
            self.send_error(404)
            return
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            payload = {}
        result = routes.dispatch(path, payload)
        body = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        global _alive_armed, _alive_empty_at
        head = self.path.split('?')[0]
        if head == '/api/backup/download':
            data = backup_service.snapshot_bytes()
            if not data:
                self.send_error(404)
                return
            filename = '采购下单系统_备份_%s.db' % time.strftime('%Y%m%d_%H%M')
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Disposition',
                             "attachment; filename*=UTF-8''%s" % urllib.parse.quote(filename))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if head.startswith('/media/') or head.startswith('/图片/'):
            self._serve_media(head)
            return
        if head in ('/__alive', '/__alive/'):
            self._sse_alive(self._query())
            return
        if head in routes.GET_PATHS:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            params = {k: v[0] for k, v in query.items() if v}
            body = json.dumps(routes.dispatch(head, params), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if head in ('/__bye', '/__bye/'):
            self._client_bye(self._query())
            return
        if head in ('/__arm', '/__arm/'):
            # 双击快捷方式时通知常驻实例：这次也按“关网页就退出”处理
            _alive_armed = True
            _alive_empty_at = None
            log('收到指令：启用关闭网页自动退出')
            body = b'armed'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if head in ('/__rebuild', '/__rebuild/'):
            try:
                meta = sqlite_store.catalog_meta()
                body = ('数据库正常：产品 %d 个，供应商 %d 家，指纹 %s。'
                        '页面已改为实时查询，不再需要重建缓存。'
                        % (meta['products'], meta['suppliers'], meta['stamp'])).encode('utf-8')
                self.send_response(200)
            except Exception as e:
                body = ('数据库检查失败：%s' % e).encode('utf-8')
                self.send_response(500)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split('?')[0] in ('/__stop', '/__stop/'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'stopped')
            log('收到退出指令')
            STOP.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path.split('?')[0] in ('/__ping', '/__ping/'):
            # 带项目根目录和版本：启动器据此判断这个端口是不是「本目录的实例」，
            # 页面右上角也用它显示「现在打开的是哪一份系统」。
            body = ('pong|' + ROOT + '|' + APP_VER + '|' + APP_ID).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split('?')[0] in ('/__stamp', '/__stamp/'):
            body = archive_service.data_stamp().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


def _arm_auto_stop(port):
    """让已经在跑的实例也支持“关掉网页就退出”"""
    try:
        OPENER.open('http://127.0.0.1:%d/__arm' % port, timeout=2).read()
        log('已通知实例 %d：启用关闭网页自动退出' % port)
    except Exception as e:
        log('通知自动退出失败: %r' % (e,))


def _watch_pages(httpd):
    """所有页面都关掉后自动退出；刷新页面会在宽限期内重连，不会误关"""
    global _alive_empty_at
    log('页面在线监测已启动（关掉网页 %.0f 秒后自动退出）' % AUTO_STOP_GRACE)
    while not STOP.is_set():
        if STOP.wait(0.5):
            break
        if not (_alive_armed and _alive_seen):
            continue
        with _alive_lock:
            online = len(_alive)
        if online:
            if _alive_empty_at is not None:
                log('页面已重新连上（刷新/新标签），取消自动退出')
            _alive_empty_at = None
            continue
        if _alive_empty_at is None:
            _alive_empty_at = time.time()
            log('页面已全部关闭，%.0f 秒后自动退出' % AUTO_STOP_GRACE)
        elif time.time() - _alive_empty_at >= AUTO_STOP_GRACE:
            log('页面关闭超过 %.0f 秒，自动退出' % AUTO_STOP_GRACE)
            STOP.set()
            try:
                httpd.shutdown()
            except Exception:
                pass
            return


def _drop_old_folder_icon():
    """清掉旧版为“文件夹换图标”写的 desktop.ini 和目录系统属性

    新版已不再写 desktop.ini（安全软件会当成木马伪装文件夹反复弹窗）。
    这里只做一次性善后：本来干净时不做任何写操作，失败也不影响启动。
    """
    try:
        tools = str(config.TOOLS_DIR)
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import _创建快捷方式
        _创建快捷方式.restore_folder_appearance()
    except Exception:
        pass


def main():
    log('---- 启动 ----')
    _drop_old_folder_icon()
    try:
        sqlite_store.ensure_database()
        log('SQLite 已就绪: %s' % sqlite_store.DB_PATH)
    except Exception as e:
        log('SQLite 初始化失败: %r' % (e,))
        _msgbox('数据库初始化失败：%s' % e)
        return

    try:
        copied = media.ensure_migrated()
        if copied:
            log('图片已迁移到 data/media：%d 张' % copied)
    except Exception as e:
        log('图片迁移失败（不影响使用）: %r' % (e,))

    try:
        backup_service.daily_if_needed()
    except Exception as e:
        log('每日备份失败（不影响使用）: %r' % (e,))

    if not os.path.exists(os.path.join(WEB, 'index.html')):
        _msgbox('找不到网页文件 web\\index.html，文件夹不完整，请重新解压。')
        return

    # 第一次使用：没有产品时打开向导页，由页面完成导入/恢复
    first_run = sqlite_store.product_count() == 0
    if first_run:
        log('数据库中还没有产品，打开首启向导')

    running = already_running()
    if running:
        log('已有实例在 %d，直接打开浏览器' % running)
        if not NO_BROWSER:
            _arm_auto_stop(running)
        open_in_browser(running, '/welcome.html' if first_run else None)
        return

    # 本目录没有实例：先把别的目录（旧系统）的实例停掉，独占 8899
    stopped = take_over_others()
    if stopped:
        log('接管完成：停掉 %d 个其它副本的实例' % len(stopped))

    port = find_port()
    if port is None:
        _msgbox('端口 8899-8930 都被占用，请重启电脑后再试。')
        return

    os.chdir(WEB)
    httpd = http.server.ThreadingHTTPServer(
        ('127.0.0.1', port), functools.partial(Handler))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    landing = '/welcome.html' if first_run else OPEN_PATH
    log('服务已启动: http://127.0.0.1:%d%s' % (port, landing))
    threading.Thread(target=_watch_pages, args=(httpd,), daemon=True).start()
    open_in_browser(port, landing)

    while not STOP.is_set():
        time.sleep(0.5)

    log('服务已结束')
    try:
        httpd.server_close()
    except Exception:
        pass


def _msgbox(text, icon=0x10):
    """无窗口模式下用系统弹窗提示（ctypes MessageBox）"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, '采购下单系统', icon)
    except Exception:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('异常: %r' % (e,))
        _msgbox('启动失败：%s\n请双击「工具\\诊断问题.bat」并把诊断报告发给小简。' % e)
