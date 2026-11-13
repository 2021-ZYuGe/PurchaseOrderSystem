# -*- coding: utf-8 -*-
"""
采购下单系统 · 静默启动（配 pythonw.exe 使用，不弹黑窗口）

用法：双击桌面「采购下单系统」图标。
特性：
  1. 不弹命令行窗口（由 pythonw.exe 运行）
  2. 自动开浏览器到系统页面
  3. 已经在运行就直接用现有的，不会重复启动（双击两次也没事）
  4. 数据文件强制不缓存，避免出现"数据只剩几条"的旧缓存问题
  5. 可用桌面「退出采购下单系统」图标干净关闭
  6. 一台电脑只跑一份：发现旧文件夹 / 旧代码的实例，先停掉再接管 8899
"""
import functools
import hashlib
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

import sqlite_store

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
WEB = os.path.join(ROOT, 'web')
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
LOG = os.path.join(ROOT, 'data', '_运行日志.txt')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
APP_VER = '2026-11-13'      # 版本日期：页面右上角会显示，用来一眼区分新旧系统
CREATE_NO_WINDOW = 0x08000000
# 想故意同时开两份（调试用）时，设环境变量 CAIGOU_ALLOW_MULTI=1
ALLOW_MULTI = os.environ.get('CAIGOU_ALLOW_MULTI') == '1'

# 程序指纹：关键文件一变就变。用来识别"文件换了但旧进程还在跑"的僵尸实例，
# 免得忘记改版本号时又连回旧代码。
STAMP_FILES = ['工具/打开系统_静默.py', '工具/生成主合同.py', '工具/sqlite_store.py',
               'web/index.html', 'web/app.js', 'web/contract.html']


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
_alive_armed = AUTO_STOP           # 是否允许“关网页就退出”
_alive_empty_at = None             # 从什么时候起没有页面了


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


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


# ---------------- 主合同相关接口 ----------------
_gen_cache = {}


def _load_gen():
    """按需加载生成器模块；源文件一改动就自动重载，不用重启服务"""
    src = os.path.join(HERE, '生成主合同.py')
    try:
        stamp = os.path.getmtime(src)
    except Exception:
        stamp = 0
    if _gen_cache.get('m') is None or _gen_cache.get('t') != stamp:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location('gen_hetong', src)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        except Exception as e:
            log('加载生成器失败：%r' % (e,))
            if _gen_cache.get('m') is not None:
                return _gen_cache['m']          # 保留上一个可用版本
            raise
        _gen_cache['m'] = m
        _gen_cache['t'] = stamp
    return _gen_cache['m']


def _norm_name(s):
    """供应商名归一化：括号全半角、空格、书名号都去掉"""
    s = str(s or '').strip()
    s = s.replace('（', '(').replace('）', ')')
    s = s.replace('　', '').replace(' ', '')
    s = s.replace('【', '').replace('】', '')
    return s


def _parse_money(s):
    m = re.search(r'([\d,]+(?:\.\d+)?)', str(s or ''))
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except Exception:
        return None


def _contract_dates():
    """合同号/文件名 -> 最近签署日期（来自 SQLite）"""
    dates = {}
    try:
        records = sqlite_store.get_contract_records()
    except Exception:
        return dates
    for r in records:
        ds = []
        if r.get('主合同日期'):
            ds.append(str(r['主合同日期']))
        ds += [str(x) for x in (r.get('签署日期') or []) if x]
        dt = max(ds) if ds else ''
        if not dt:
            continue
        for key in (r.get('合同号'), r.get('文件名')):
            if key:
                k = str(key)
                if dt > dates.get(k, ''):
                    dates[k] = dt
    return dates


def _last_order_amounts():
    """供应商 -> 最近一份合同的总金额

    金额优先从「付款方式」里的“本产品订单总金额为 X 元”取；
    没有这句话时，退回把该合同各产品行的「总金额」相加。
    """
    dates = _contract_dates()
    groups = {}
    try:
        recs = sqlite_store.get_historical_order_items()
    except Exception:
        return {}
    for r in recs:
        supplier = str(r.get('供应商') or '').strip()
        if not supplier:
            continue
        contract = str(r.get('合同号') or r.get('文件名') or '').strip()
        g = groups.setdefault((supplier, contract), {'amount': None, 'sum': 0.0, 'date': ''})
        pay = str(r.get('付款方式') or '')
        m = re.search(r'本产品订单总金额为\s*([\d,]+(?:\.\d+)?)\s*元', pay)
        if m and g['amount'] is None:
            try:
                g['amount'] = float(m.group(1).replace(',', ''))
            except Exception:
                pass
        amt = _parse_money(r.get('总金额'))
        if amt is not None:
            g['sum'] += amt
        dt = dates.get(contract) or dates.get(str(r.get('文件名') or '')) or ''
        if dt > g['date']:
            g['date'] = dt

    best = {}
    for (supplier, contract), g in groups.items():
        amount = g['amount'] if g['amount'] is not None else (g['sum'] or None)
        if amount is None:
            continue
        nk = _norm_name(supplier)
        rank = (g['date'] or '', contract)
        cur = best.get(nk)
        if cur is None or rank > cur[0]:
            best[nk] = (rank, amount, g['date'])
    return {k: {'amount': v[1], 'date': v[2]} for k, v in best.items()}


def load_archive():
    """从 SQLite 读取供应商档案（续签时自动带入旧信息用）"""
    try:
        d = sqlite_store.get_supplier_archive()
    except Exception:
        return {'suppliers': [], 'party_a': {}}
    sup = d.get('供应商') or []
    sup.sort(key=lambda x: x.get('最近签署日期') or '', reverse=True)
    # 甲方默认取最近模板里那套
    ja = d.get('甲方备选') or {}
    party_a = {}
    for n, v in ja.items():
        if '甲方公司' in n:
            if (v.get('最近签署日期') or '') > (party_a.get('最近签署日期') or ''):
                party_a = v
    last_amounts = _last_order_amounts()
    last_keys = list(last_amounts.keys())
    light = []
    for s in sup:
        name = s.get('名称', '')
        item = {
            'name': name,
            'credit_code': s.get('统一社会信用代码', ''),
            'contact': s.get('联系人', ''),
            'tel': s.get('电话', ''),
            'email': s.get('邮箱', ''),
            'addr': s.get('地址', ''),
            'wechat': s.get('微信号', ''),
            'legal': s.get('法定代表人', ''),
            'bank_name': s.get('对公账户名') or name,
            'bank_account': s.get('对公账号', ''),
            'bank_open': s.get('开户行', ''),
            'last_sign': s.get('最近签署日期', ''),
        }
        nk = _norm_name(name)
        match = nk if nk and nk in last_amounts else None
        if not match and nk and '甲方公司' not in nk:
            cands = [k for k in last_keys if nk.startswith(k) or k.startswith(nk)]
            if cands:
                # 优先公共前缀最长、长度差最小的，避免“优尚”误配到别的公司
                match = max(cands, key=lambda k: (len(os.path.commonprefix([nk, k])), -abs(len(nk) - len(k))))
        if match:
            item['last_order_amount'] = last_amounts[match]['amount']
            item['last_order_date'] = last_amounts[match]['date']
        light.append(item)
    return {'suppliers': light, 'party_a': party_a}


def save_supplier(info):
    """新签或修改后写入 SQLite，空字段不会清除原有内容。"""
    try:
        return sqlite_store.save_supplier_profile(info or {})
    except Exception as e:
        log('保存供应商到 SQLite 失败: %r' % (e,))
        return False


def data_stamp():
    """SQLite 目录修订指纹：数据更新后页面可据此刷新。"""
    try:
        return sqlite_store.database_stamp()
    except Exception:
        return '0'


def open_in_browser(port):
    """关键：URL 带时间戳，避免浏览器复用同网址的旧标签页（不刷新）"""
    if NO_BROWSER:
        log('本次设定：不自动打开浏览器')
        return ''
    url = 'http://127.0.0.1:%d%s?t=%d' % (port, OPEN_PATH, int(time.time() * 1000))
    try:
        webbrowser.open(url)
    except Exception as e:
        log('打开浏览器失败: %r' % (e,))
    return url


# ---------------- 一键更新：扫描到的新合同写进数据库 ----------------
SYNC_LOCK = threading.Lock()
SYNC_STATE = {"state": "idle", "total": 0, "started": "", "finished": "", "message": ""}
SYNC_PY = os.path.join(ROOT, '运行环境', 'python.exe')
if not os.path.exists(SYNC_PY):
    SYNC_PY = sys.executable


def _sync_status():
    with SYNC_LOCK:
        return dict(SYNC_STATE)


def _set_sync(**kw):
    with SYNC_LOCK:
        SYNC_STATE.update(kw)


def _start_sync():
    items = sqlite_store.scan_pending_contracts().get("路径清单") or []
    if not items:
        return {"ok": False, "error": "没有检测到需要导入的新合同"}
    with SYNC_LOCK:
        if SYNC_STATE.get("state") == "running":
            return {"ok": False, "error": "正在更新中，请稍候"}
        SYNC_STATE.update({
            "state": "running", "total": len(items), "started": time.strftime("%H:%M:%S"),
            "finished": "", "message": "正在解析 %d 份合同…" % len(items),
        })
    threading.Thread(target=_sync_worker, args=(items,), daemon=True).start()
    return {"ok": True, "total": len(items)}


def _sync_worker(items):
    groups = {}
    for item in items:
        path = item.get("路径") or ""
        if not path:
            continue
        root = item.get("根") or os.path.dirname(path)
        groups.setdefault(root, []).append(path)
    log("一键更新开始：%d 份合同 / %d 个来源目录" % (len(items), len(groups)))

    messages, ok_all = [], True
    for root, paths in groups.items():
        listfile = os.path.join(ROOT, 'data', '_待导入清单_%d.txt' % int(time.time() * 1000))
        try:
            with open(listfile, 'w', encoding='utf-8') as f:
                f.write("\n".join(paths))
            cmd = [SYNC_PY, os.path.join(HERE, '合并新合同.py'),
                   '--files', listfile, '--yes', root]
            result = subprocess.run(
                cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800,
            )
            text = result.stdout.decode('gbk', errors='replace')
            if "合并完成" in text:
                messages.append("导入 %d 份成功" % len(paths))
            else:
                ok_all = False
                tail = " / ".join([ln.strip() for ln in text.strip().splitlines() if ln.strip()][-2:])
                messages.append("导入失败：%s" % (tail or "未知错误"))
                log("一键更新失败（%s）：%s" % (root, tail))
        except Exception as e:
            ok_all = False
            messages.append("导入异常：%s" % e)
            log("一键更新异常：%r" % (e,))
        finally:
            try:
                if os.path.exists(listfile):
                    os.remove(listfile)
            except OSError:
                pass

    sqlite_store.clear_pending_cache()
    try:
        sqlite_store.export_data_js()
    except Exception as e:
        log("一键更新后重建缓存失败：%r" % (e,))
    message = "；".join(messages)[:300]
    _set_sync(state="done" if ok_all else "error",
              finished=time.strftime("%H:%M:%S"), message=message)
    log("一键更新结束：%s" % message)


class Handler(http.server.SimpleHTTPRequestHandler):
    """禁止缓存 + 支持远程关闭 + 主合同生成接口"""

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
        if not path.startswith('/api/'):
            self.send_error(404)
            return
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            payload = {}
        result = self._api(path, payload)
        body = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api(self, path, p):
        try:
            if path == '/api/archive':
                return {'ok': True, 'data': load_archive()}
            if path == '/api/make_contract':
                gen = _load_gen()
                res = gen.make_contract(p)
                if p.get('remember'):
                    save_supplier(p.get('party_b') or {})
                log('生成主合同: %s' % res.get('name'))
                return res
            if path == '/api/make_info_sheet':
                gen = _load_gen()
                res = gen.make_info_sheet(p)
                log('生成信息收集表: %s' % res.get('name'))
                return res
            if path == '/api/contract_status':
                # 数据新鲜度 + 来源目录里还没导入的合同
                return {'ok': True, 'data': {
                    'freshness': sqlite_store.data_freshness(),
                    'pending': sqlite_store.scan_pending_contracts(),
                }}
            if path == '/api/contract_expiry':
                return {'ok': True, 'data': sqlite_store.contract_expiry_overview()}
            if path == '/api/save_contract_term':
                res = sqlite_store.save_contract_term(
                    p.get('供应商') or p.get('supplier') or '',
                    p.get('起始日') or p.get('start') or '',
                    p.get('到期日') or p.get('end') or '',
                    p.get('备注') or p.get('note') or '',
                )
                sqlite_store.export_data_js()
                log('登记合同期限：%s 至 %s' % (res.get('供应商'), res.get('到期日')))
                return {'ok': True, 'data': res,
                        'overview': sqlite_store.contract_expiry_overview()}
            if path == '/api/delete_contract_term':
                res = sqlite_store.delete_contract_term(p.get('供应商') or p.get('supplier') or '')
                sqlite_store.export_data_js()
                log('撤销合同期限登记：%s' % res.get('供应商'))
                return {'ok': True, 'data': res,
                        'overview': sqlite_store.contract_expiry_overview()}
            if path == '/api/sync_contracts':
                return _start_sync()
            if path == '/api/sync_status':
                return {'ok': True, 'data': _sync_status()}
            if path == '/api/save_supplier':
                return {'ok': save_supplier(p or {})}
            return {'ok': False, 'error': '未知接口 ' + path}
        except Exception as e:
            try:
                import traceback
                log('接口异常 %s: %r\n%s' % (path, e, traceback.format_exc()))
            except Exception:
                pass
            return {'ok': False, 'error': '%s' % e}
        finally:
            # 生成器里若有人改动 sys.stdout，这里把它恢复到可用状态，避免后续日志写坏
            try:
                import io as _io
                if getattr(sys, 'stdout', None) is None or getattr(sys.stdout, 'closed', False):
                    sys.stdout = _io.StringIO()
            except Exception:
                pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        global _alive_armed, _alive_empty_at
        head = self.path.split('?')[0]
        if head in ('/__alive', '/__alive/'):
            self._sse_alive(self._query())
            return
        if head in ('/api/contract_status', '/api/sync_status', '/api/contract_expiry'):
            body = json.dumps(self._api(head, {}), ensure_ascii=False).encode('utf-8')
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
                products, suppliers, stamp = sqlite_store.export_data_js()
                body = ('已从 SQLite 重新生成网页缓存：产品 %d 个，供应商 %d 家，指纹 %s'
                        % (products, suppliers, stamp)).encode('utf-8')
                self.send_response(200)
            except Exception as e:
                body = ('缓存生成失败：%s' % e).encode('utf-8')
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
            body = data_stamp().encode('utf-8')
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
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
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

    if not os.path.exists(os.path.join(WEB, 'index.html')):
        _msgbox('找不到网页文件 web\\index.html，文件夹不完整，请重新解压。')
        return

    # 第一次使用：SQLite 中还没有产品，直接引导导入。
    if sqlite_store.product_count() == 0:
        log('SQLite 中还没有产品，引导数据导入')
        _msgbox('第一次使用，还没有你的合同数据。\n\n'
                '点「确定」后会弹出数据导入窗口（黑色窗口）：\n'
                '把你自己导出的合同文件夹路径粘贴进去，回车即可。\n\n'
                '导入完成后，再双击一次「工具\\打开系统.py」就能用了。',
                icon=0x40)
        try:
            import subprocess
            subprocess.Popen([os.path.join(ROOT, '运行环境', 'python.exe'),
                              os.path.join(HERE, '更新数据源.py')], cwd=ROOT)
        except Exception as e:
            log('拉起数据导入失败: %r' % (e,))
            _msgbox('没能自动打开数据导入窗口，请手动双击「工具\\更新数据源.py」。')
        return

    running = already_running()
    if running:
        log('已有实例在 %d，直接打开浏览器' % running)
        if not NO_BROWSER:
            _arm_auto_stop(running)
        open_in_browser(running)
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

    log('服务已启动: http://127.0.0.1:%d/index.html' % port)
    threading.Thread(target=_watch_pages, args=(httpd,), daemon=True).start()
    open_in_browser(port)

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
        _msgbox('启动失败：%s\n请双击「工具\\诊断问题.bat」并把诊断报告发给管理员。' % e)
