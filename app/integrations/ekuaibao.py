# -*- coding: utf-8 -*-
"""易快报（合思）合同附件客户端。

用链接里的 accessToken 直接调用易快报接口：
单据列表 → 单据详情 → 附件签名直链 → 下载。
不模拟点击、不需要浏览器，也不需要第三方库（只用标准库 urllib）。

本模块只负责"和易快报说话"，批次编排在 services/imports.py。
"""
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

STATE_GROUPS = {
    'active': ['rejected', 'draft', 'sending', 'receiving', 'receivingExcep',
               'approving', 'pending', 'paying'],
    'done': ['completed', 'archived'],
    'paid': ['paid'],
}
ALL_STATES = [s for g in ('active', 'done', 'paid') for s in STATE_GROUPS[g]]
LEGACY_ALL_FILTER = '1==1'
DEFAULT_DELAY = 1.0
BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


class AuthError(Exception):
    """token 失效或被拒绝"""


def state_filter(states):
    return '(state.in(%s))' % ','.join('"%s"' % s for s in states)


def parse_link(url):
    """从粘贴的地址里取出 base / corpId / accessToken"""
    parsed = urllib.parse.urlparse(str(url or '').strip())
    qs = urllib.parse.parse_qs(parsed.query)
    # 有的链接把参数放在 # 之后（#/workspace?accessToken=…），两处都要看
    if '?' in parsed.fragment:
        for key, value in urllib.parse.parse_qs(parsed.fragment.split('?', 1)[1]).items():
            qs.setdefault(key, value)
    corp = (qs.get('ekbCorpId') or qs.get('corpId') or [''])[0]
    token = (qs.get('accessToken') or qs.get('accesstoken') or [''])[0]
    base = '%s://%s' % (parsed.scheme, parsed.netloc) if parsed.scheme and parsed.netloc \
        else 'https://wx2.ekuaibao.com'
    return base, corp, token


def safe_name(name, maxlen=120):
    name = BAD_CHARS.sub('_', name or '未命名').strip().strip('.')
    if len(name) > maxlen:
        stem, dot, ext = name.rpartition('.')
        if dot and len(ext) <= 6:
            name = stem[:maxlen - len(ext) - 1] + '.' + ext
        else:
            name = name[:maxlen]
    return name


def strip_suffix(name):
    """内部 key 形如 xxx-1793862012472-723.docx，展示名才是真名"""
    return re.sub(r'-\d{13}-\d+(\.[A-Za-z0-9]{1,6})$', r'\1', name)


def collect_file_fields(node, acc):
    """递归找出详情里所有 {fileId, fileName} 结构的附件"""
    if isinstance(node, dict):
        fid = node.get('fileId')
        fname = node.get('fileName') or node.get('name') or node.get('key')
        if isinstance(fid, str) and fid and fname:
            acc.append({'fileId': fid, 'fileName': str(fname)})
            return
        for value in node.values():
            collect_file_fields(value, acc)
    elif isinstance(node, list):
        for value in node:
            collect_file_fields(value, acc)


def group_of(state):
    for key, states in STATE_GROUPS.items():
        if state in states:
            return {'active': '在途', 'done': '已完成', 'paid': '已支付'}[key]
    return state or '其他'


class Throttle:
    """固定间隔 + 抖动；被限流时整体放慢，避免形成高频访问特征"""

    def __init__(self, base=DEFAULT_DELAY, cap=6.0):
        self.base = max(0.0, base)
        self.cur = self.base
        self.cap = cap
        self.last = 0.0
        self.slowed = 0

    def wait(self):
        if self.cur > 0:
            gap = self.cur * random.uniform(0.8, 1.4)
            delta = time.time() - self.last
            if delta < gap:
                time.sleep(gap - delta)
        self.last = time.time()

    def slow_down(self, factor=1.8):
        self.cur = min(self.cap, max(self.base, self.cur) * factor)
        self.slowed += 1


class UrllibTransport:
    """标准库 HTTP 传输层；测试里可以替换成假实现"""

    def call(self, method, url, headers=None, body=None, timeout=60):
        request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            try:
                data = e.read()
            except Exception:
                data = b''
            return e.code, dict(e.headers or {}), data
        except urllib.error.URLError as e:
            raise RuntimeError('网络错误：%s' % (e.reason,))

    def download(self, url, path, timeout=120):
        tmp = path + '.part'
        total = 0
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp, open(tmp, 'wb') as fh:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
        except urllib.error.HTTPError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError('HTTP %s' % e.code)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        if total == 0:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError('下载内容为空')
        os.replace(tmp, path)
        return total


class Ekb:
    def __init__(self, base, corp, token, referer='', throttle=None, transport=None):
        self.base = base.rstrip('/')
        self.corp = corp
        self.token = token
        self.t = throttle or Throttle()
        self.transport = transport or UrllibTransport()
        self.headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'accesstoken': token,
            'corpid': corp,
            'user-agent': UA,
            'origin': self.base,
            'referer': referer or self.base,
        }
        self.last_total = 0

    def _url(self, path, params=None):
        url = self.base + path
        if params:
            url += '?' + urllib.parse.urlencode(params)
        return url

    def open_session(self):
        status, _headers, raw = self.transport.call(
            'GET',
            self._url('/api/account/v2/session',
                      {'accessToken': self.token, 'corpId': self.corp}),
            headers=self.headers, timeout=30)
        if status in (401, 403):
            raise AuthError('token 已失效')
        if status != 200:
            raise RuntimeError('会话建立失败：HTTP %s' % status)
        try:
            value = (json.loads(raw.decode('utf-8', 'replace')) or {}).get('value') or {}
        except ValueError:
            raise RuntimeError('会话返回异常，可能链接不完整')
        if not value.get('userId'):
            raise AuthError('token 已失效')
        return True

    def who_am_i(self):
        try:
            status, _h, raw = self.transport.call(
                'GET',
                self._url('/api/v1/organization/staffs/me',
                          {'corpId': self.corp, 'type': 'check'}),
                headers=self.headers, timeout=20)
            if status != 200:
                return ''
            value = (json.loads(raw.decode('utf-8', 'replace')) or {}).get('value') or {}
            return ((value.get('staff') or {}).get('name') or '').strip()
        except Exception:
            return ''

    def _post(self, path, body, what, params=None, retry=3):
        url = self._url(path, params)
        payload = json.dumps(body).encode('utf-8')
        last = None
        for attempt in range(retry + 1):
            try:
                self.t.wait()
                status, headers, raw = self.transport.call(
                    'POST', url, headers=self.headers, body=payload, timeout=60)
                if status in (401, 403):
                    raise AuthError('token 已失效')

                if status == 429 or status >= 500:
                    if attempt < retry:
                        wait = self._retry_after(headers, attempt)
                        self.t.slow_down()
                        time.sleep(wait)
                        continue
                    raise RuntimeError('%s失败：HTTP %s（重试 %d 次仍失败，稍后再跑）'
                                       % (what, status, retry))

                if status != 200:
                    raise RuntimeError('%s失败：HTTP %s %s'
                                       % (what, status, raw[:150].decode('utf-8', 'replace')))
                data = json.loads(raw.decode('utf-8', 'replace'))
                if isinstance(data, dict) and data.get('errorCode') in (401, 403):
                    raise AuthError(str(data.get('errorMessage') or 'token 已失效'))
                return data
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
                if attempt < retry:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise RuntimeError('%s网络错误：%s' % (what, e))
        raise RuntimeError(str(last))

    @staticmethod
    def _retry_after(headers, attempt):
        value = (headers or {}).get('Retry-After') or (headers or {}).get('retry-after')
        if value:
            try:
                return min(60.0, float(value))
            except (TypeError, ValueError):
                pass
        return min(30.0, 2.0 ** (attempt + 1) + random.random())

    def list_bills(self, filter_by=None, page_size=200, max_pages=60):
        filter_by = filter_by or state_filter(ALL_STATES)
        out, seen, start, total = [], set(), 0, None
        for _ in range(max_pages):
            body = {'filterBy': filter_by,
                    'limit': {'start': start, 'count': page_size}}
            data = self._post('/api/flow/v1/flows/my', body, '查询单据列表',
                              params={'type': 'home5', 'delegatedFilter': 'DELEGATE_TO_ME',
                                      'corpId': self.corp})
            items = data.get('items') or []
            if total is None:
                total = data.get('count')
            new = 0
            for item in items:
                fid = (item.get('flow') or {}).get('id')
                if fid and fid not in seen:
                    seen.add(fid)
                    out.append(item)
                    new += 1
            if len(items) < page_size or new == 0:
                break
            start += len(items)
        self.last_total = total or len(out)
        return out

    def bill_detail(self, flow_id):
        data = self._post('/api/flow/v1/flows/flowId/$' + flow_id,
                          {'filterBy': '(id=="%s")' % flow_id}, '查询单据详情',
                          params={'id': flow_id, 'corpId': self.corp})
        return data.get('value') or {}

    def resolve_files(self, ids):
        out = {}
        for i in range(0, len(ids), 50):
            data = self._post('/api/v1/attachment/attachments/ids',
                              {'ids': ids[i:i + 50]}, '解析附件地址',
                              params={'corpId': self.corp})
            for item in data.get('items') or []:
                out[item.get('id')] = item
        return out

    def download(self, url, path, timeout=120):
        self.t.wait()
        return self.transport.download(url, path, timeout=timeout)


def select_targets(items, template='合同审批流程', since='', limit=0, codes=None):
    """按模板 / 日期 / 数量 / 单号筛选要处理的单据"""
    since_ts = None
    if since:
        try:
            since_ts = datetime.strptime(since, '%Y-%m-%d').timestamp() * 1000
        except ValueError:
            raise RuntimeError('日期格式应为 YYYY-MM-DD：%s' % since)

    targets = []
    for item in items:
        form = item.get('form') or {}
        if ((form.get('specification') or {}).get('name') or '') != template:
            continue
        submitted = form.get('submitDate') or 0
        if since_ts and submitted < since_ts:
            continue
        targets.append({
            'flow_id': (item.get('flow') or {}).get('id'),
            'code': form.get('code') or '',
            'title': form.get('title') or '',
            'state': (item.get('flow') or {}).get('state') or '',
            'submit': datetime.fromtimestamp(submitted / 1000).strftime('%Y-%m-%d')
                      if submitted else '',
        })
    if limit:
        targets = targets[:int(limit)]
    if codes:
        wanted = {c.strip().upper() for c in str(codes).replace('，', ',').split(',') if c.strip()}
        targets = [t for t in targets if (t['code'] or '').upper() in wanted]
    return targets
