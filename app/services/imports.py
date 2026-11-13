# -*- coding: utf-8 -*-
"""批次导入：下载 → 校验 → 解析 → 入库，一套流程。

两种来源共用同一套批次与报告：
  * ekuaibao  粘贴易快报链接，自动下载合同附件
  * folder    直接指定本地文件夹（增量导入）

真正的解析/合并仍复用 工具/合并新合同.py，避免两套入库逻辑。
"""
import csv
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import app.config as config
from app.infra import store
from app.infra.logging import log
from app.integrations import ekuaibao

_LOCK = threading.Lock()
_STATE = {
    'state': 'idle',        # idle / running / done / error
    'phase': '',            # listing / downloading / importing
    'message': '',
    'error': '',
    'done': 0,
    'total': 0,
    'batch': '',
    'started': '',
    'finished': '',
    'result': None,
}
MAX_LOG_TAIL = 8


def _set(**kw):
    with _LOCK:
        _STATE.update(kw)


def status():
    with _LOCK:
        data = dict(_STATE)
    data['products'] = store.product_count()
    return data


def _root():
    folder = Path(store.DATA_DIR) / 'imports'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _new_batch(source):
    batch_id = time.strftime('%Y%m%d_%H%M%S')
    folder = _root() / batch_id
    suffix = 1
    while folder.exists():
        suffix += 1
        folder = _root() / ('%s_%d' % (batch_id, suffix))
    folder.mkdir(parents=True)
    return folder.name, folder


def _save_meta(folder, meta):
    try:
        (folder / 'batch.json').write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8', newline='\n')
    except OSError as e:
        log('写入批次信息失败：%r' % (e,))


def _opts(payload):
    def as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def as_float(value, default=1.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    scope = payload.get('scope')
    if scope not in ('all', 'active', 'done', 'paid'):
        scope = 'all'
    keyword = payload.get('keyword')
    return {
        'template': str(payload.get('template') or '').strip() or '合同审批流程',
        'keyword': '合同' if keyword is None else str(keyword),
        'since': str(payload.get('since') or '').strip(),
        'scope': scope,
        'limit': max(0, as_int(payload.get('limit'), 0)),
        'delay': min(6.0, max(0.3, as_float(payload.get('delay'), 1.0))),
        'include_duplicates': bool(payload.get('include_duplicates')),
    }


def _state_filter(scope):
    if scope == 'all':
        return ekuaibao.state_filter(ekuaibao.ALL_STATES)
    return ekuaibao.state_filter(ekuaibao.STATE_GROUPS[scope])


def _list_bills(client, scope):
    """按状态取单据；服务端不认显式状态条件时退回兼容写法"""
    try:
        return client.list_bills(_state_filter(scope))
    except Exception:
        if scope != 'all':
            raise
        return client.list_bills(ekuaibao.LEGACY_ALL_FILTER)


def _split_duplicates(targets, known):
    new, duplicates = [], []
    for item in targets:
        code = (item.get('code') or '').upper()
        if code and code in known:
            duplicates.append(item)
        else:
            new.append(item)
    return new, duplicates


def preview_ekb(payload):
    """只读预览：连接、取列表、判断新增/重复，不下载任何文件"""
    url = str(payload.get('url') or '').strip()
    if not url:
        return {'ok': False, 'error': '请先粘贴易快报链接'}
    if 'accessToken' not in url and 'accesstoken' not in url:
        return {'ok': False, 'error': '链接里没有 accessToken，请重新复制完整链接'}
    base, corp, token = ekuaibao.parse_link(url)
    if not token or not corp:
        return {'ok': False, 'error': '链接解析失败：缺少 accessToken 或 ekbCorpId'}

    options = _opts(payload)
    client = ekuaibao.Ekb(base, corp, token, referer=url,
                          throttle=ekuaibao.Throttle(options['delay']))
    try:
        client.open_session()
    except ekuaibao.AuthError:
        return {'ok': False, 'error': '这个链接已经过期，请在企业微信里重新复制'}
    except Exception as e:
        return {'ok': False, 'error': '连接易快报失败：%s' % e}

    who = client.who_am_i()
    try:
        items = _list_bills(client, options['scope'])
        targets = ekuaibao.select_targets(
            items, template=options['template'], since=options['since'],
            limit=options['limit'])
    except Exception as e:
        log('预览读取单据失败：%r\n%s' % (e, traceback.format_exc()))
        return {'ok': False, 'error': '读取单据失败：%s' % e}

    known = store.known_contract_numbers()
    new, duplicates = _split_duplicates(targets, known)
    samples = [dict(t, is_new=True) for t in new[:25]]
    samples += [dict(t, is_new=False) for t in duplicates[:10]]

    return {'ok': True, 'data': {
        'who': who,
        'total_bills': len(items),
        'matching': len(targets),
        'new': len(new),
        'duplicates': len(duplicates),
        'samples': samples,
        'duplicate_codes': [t['code'] for t in duplicates[:20] if t['code']],
        'template': options['template'],
        'since': options['since'],
        'scope': options['scope'],
    }}


def start_ekb(payload):
    url = str(payload.get('url') or '').strip()
    if 'accessToken' not in url and 'accesstoken' not in url:
        return {'ok': False, 'error': '请粘贴含 accessToken 的易快报链接'}
    with _LOCK:
        if _STATE['state'] == 'running':
            return {'ok': False, 'error': '已有导入任务在跑，请等它结束'}

    options = _opts(payload)
    batch_id, folder = _new_batch('ekuaibao')
    _set(state='running', phase='listing', message='正在连接易快报…', error='',
         done=0, total=0, batch=batch_id, started=time.strftime('%H:%M:%S'),
         finished='', result=None)
    threading.Thread(target=_run_ekb, args=(url, options, batch_id, folder),
                     daemon=True).start()
    return {'ok': True, 'data': {'batch': batch_id}}


def _run_ekb(url, options, batch_id, folder):
    meta = {
        'id': batch_id,
        'source': 'ekuaibao',
        'created': time.strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'running',
        'template': options['template'],
        'keyword': options['keyword'],
        'since': options['since'],
        'scope': options['scope'],
        'stats': {},
        'files': [],
        'import': {},
    }
    try:
        base, corp, token = ekuaibao.parse_link(url)
        client = ekuaibao.Ekb(base, corp, token, referer=url,
                              throttle=ekuaibao.Throttle(options['delay']))
        client.open_session()
        who = client.who_am_i()
        meta['who'] = who

        _set(phase='listing', message='正在读取单据列表…')
        items = _list_bills(client, options['scope'])
        targets = ekuaibao.select_targets(
            items, template=options['template'], since=options['since'],
            limit=options['limit'])
        known = store.known_contract_numbers()
        new, duplicates = _split_duplicates(targets, known)
        if not options['include_duplicates']:
            targets = new
        meta['stats'].update({
            'bills_total': len(items), 'bills_matching': len(new) + len(duplicates),
            'bills_new': len(new), 'bills_duplicate': len(duplicates),
        })
        _save_meta(folder, meta)
        if not targets:
            return _finish(folder, meta, True,
                           '没有需要导入的新合同（已完成 %d 张，重复 %d 张）'
                           % (len(new), len(duplicates)))

        # ---------- 逐张读附件 ----------
        _set(phase='downloading', total=len(targets), done=0,
             message='正在读取单据附件（共 %d 张）…' % len(targets))
        plan = []
        for index, target in enumerate(targets, 1):
            detail = client.bill_detail(target['flow_id'])
            found, seen = [], set()
            fields = []
            ekuaibao.collect_file_fields(detail.get('form') or {}, fields)
            for item in fields:
                if item['fileId'] in seen:
                    continue
                seen.add(item['fileId'])
                item['fileName'] = ekuaibao.strip_suffix(item['fileName'])
                found.append(item)
            keyword = (options['keyword'] or '').strip().lower()
            picked = [f for f in found if keyword in f['fileName'].lower()] if keyword else found
            for item in picked:
                plan.append((target, item))
            _set(done=index,
                 message='读取单据 %d/%d，已找到 %d 个附件' % (index, len(targets), len(plan)))
        meta['stats']['attachments'] = len(plan)
        _save_meta(folder, meta)
        if not plan:
            return _finish(folder, meta, True,
                           '单据里没有匹配「%s」的附件；可把关键字留空再试一次'
                           % (options['keyword'] or '全部'))

        # ---------- 解析地址并下载 ----------
        _set(phase='downloading', total=len(plan), done=0, message='正在解析下载地址…')
        links = client.resolve_files([item['fileId'] for _, item in plan])

        rows, ok, skip, fail = [], 0, 0, 0
        for index, (target, item) in enumerate(plan, 1):
            name = ekuaibao.safe_name(
                ('%s_%s' % (target['code'], item['fileName'])) if target['code'] else item['fileName'])
            path = folder / name
            row = {'单号': target['code'], '单据标题': target['title'],
                   '附件名': item['fileName'], '文件名': name, '结果': '', '大小': ''}
            if path.exists() and path.stat().st_size > 0:
                skip += 1
                row['结果'] = '已存在'
                rows.append(row)
                _set(done=index, message='下载 %d/%d：已存在，跳过' % (index, len(plan)))
                continue
            link = (links.get(item['fileId']) or {}).get('url')
            if not link:
                fail += 1
                row['结果'] = '无下载地址'
                rows.append(row)
                continue
            try:
                size = client.download(link, str(path))
            except Exception:
                # 签名直链有时效，失败就现场重新解析一次
                try:
                    fresh = (client.resolve_files([item['fileId']])
                             .get(item['fileId']) or {}).get('url')
                    if not fresh:
                        raise RuntimeError('重新解析地址失败')
                    size = client.download(fresh, str(path))
                except Exception as e:
                    fail += 1
                    row['结果'] = '失败：%s' % e
                    rows.append(row)
                    _set(done=index, message='下载 %d/%d 失败：%s' % (index, len(plan), e))
                    continue
            ok += 1
            row['结果'] = '成功'
            row['大小'] = '%.0fKB' % (size / 1024)
            rows.append(row)
            _set(done=index, message='下载 %d/%d：%s' % (index, len(plan), name))

        _write_csv(folder, rows)
        meta['stats'].update({'downloaded': ok, 'skipped': skip, 'failed': fail})
        meta['files'] = [r['文件名'] for r in rows if r.get('文件名')]
        _save_meta(folder, meta)
        if ok + skip == 0:
            return _finish(folder, meta, False, '一个附件都没下载成功')

        # ---------- 入库 ----------
        files = [str(folder / r['文件名']) for r in rows if r.get('文件名')]
        return _import_and_finish(folder, meta, files, str(folder))
    except ekuaibao.AuthError:
        return _finish(folder, meta, False, '登录态失效，请重新复制易快报链接')
    except Exception as e:
        log('易快报导入失败：%r' % (e,))
        return _finish(folder, meta, False, '导入失败：%s' % e)


def start_folder(payload):
    """本地文件夹增量导入（不下载，直接解析入库）"""
    path = str(payload.get('path') or '').strip().strip('"').strip("'")
    if not path or not Path(path).is_dir():
        return {'ok': False, 'error': '找不到这个文件夹'}
    with _LOCK:
        if _STATE['state'] == 'running':
            return {'ok': False, 'error': '已有导入任务在跑，请等它结束'}

    folder_path = Path(path)
    files = sorted(str(p) for p in folder_path.rglob('*.docx'))
    if not files:
        return {'ok': False, 'error': '这个文件夹里没有 .docx 合同'}

    batch_id, folder = _new_batch('folder')
    _set(state='running', phase='importing', message='正在解析入库…', error='',
         done=0, total=len(files), batch=batch_id, started=time.strftime('%H:%M:%S'),
         finished='', result=None)
    meta = {
        'id': batch_id, 'source': 'folder', 'path': str(folder_path),
        'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'status': 'running',
        'stats': {'files': len(files)}, 'files': files, 'import': {},
    }
    _save_meta(folder, meta)
    threading.Thread(target=_run_folder, args=(folder, meta, files, str(folder_path)),
                     daemon=True).start()
    return {'ok': True, 'data': {'batch': batch_id}}


def _run_folder(folder, meta, files, root):
    try:
        return _import_and_finish(folder, meta, files, root)
    except Exception as e:
        log('本地批次导入失败：%r' % (e,))
        return _finish(folder, meta, False, '导入失败：%s' % e)


def _import_and_finish(folder, meta, files, root):
    _set(phase='importing', total=0, done=0, message='正在解析合同并入库…')
    _save_meta(folder, meta)
    before = store.product_count()
    ok, text = _merge(files, root, folder)
    after = store.product_count()
    meta['import'] = {'ok': ok, 'tail': text[-1500:] if text else ''}
    meta['stats'].update({'products_before': before, 'products_after': after})
    _set(total=len(files), done=len(files))

    if not ok:
        return _finish(folder, meta, False, '入库失败，详情见批次报告')
    if '没有需要处理的新合同' in text:
        return _finish(folder, meta, True,
                       '这批合同都已收录，无需重复导入（产品 %d 个）' % after)
    if '合并完成' not in text:
        # 解析器返回 0 但没走完合并（例如运行环境缺失），不能算成功
        last_line = next((line.strip() for line in reversed(text.splitlines())
                          if line.strip()), '')
        return _finish(folder, meta, False, '入库未完成：%s' % last_line[:120])
    return _finish(folder, meta, True,
                   '导入完成：产品 %d → %d 个，供应商 %d 家'
                   % (before, after, len(store.list_suppliers_light())))


def _merge(files, root, folder):
    listfile = folder / '_待导入清单.txt'
    listfile.write_text('\n'.join(files), encoding='utf-8')
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    # 让合并脚本里的解析器复用当前解释器（无便携运行环境时也能跑）
    env['CAIGOU_PYTHON'] = sys.executable
    command = [sys.executable, str(config.MERGE_SCRIPT),
               '--files', str(listfile), '--yes', str(root)]
    try:
        result = subprocess.run(
            command, cwd=config.ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3600)
    except Exception as e:
        return False, '调用合并脚本失败：%s' % e
    return result.returncode == 0, _decode_output(result.stdout)


def _decode_output(raw):
    """合并脚本在管道里可能输出 GBK，也可能输出 UTF-8；两种都试。"""
    for encoding in ('utf-8', 'gbk'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def _write_csv(folder, rows):
    if not rows:
        return
    path = folder / '下载记录.csv'
    try:
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            writer = csv.writer(fh)
            writer.writerow(['单号', '单据标题', '附件名', '文件名', '结果', '大小'])
            for row in rows:
                writer.writerow([row.get('单号', ''), row.get('单据标题', ''),
                                 row.get('附件名', ''), row.get('文件名', ''),
                                 row.get('结果', ''), row.get('大小', '')])
    except OSError as e:
        log('写入下载记录失败：%r' % (e,))


def _finish(folder, meta, ok, message):
    meta['status'] = 'done' if ok else 'error'
    meta['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    meta['message'] = message
    _save_meta(folder, meta)
    _set(state='done' if ok else 'error', phase='', message=message,
         error='' if ok else message, finished=time.strftime('%H:%M:%S'),
         result={
             'id': meta.get('id', ''),
             'source': meta.get('source', ''),
             'stats': meta.get('stats', {}),
             'import': meta.get('import', {}),
             'files': len(meta.get('files') or []),
         })
    log('批次导入结束（%s）：%s' % (meta.get('id'), message))
    return {'ok': ok, 'message': message}


def history(limit=10):
    folder = Path(store.DATA_DIR) / 'imports'
    if not folder.is_dir():
        return []
    items = []
    for batch in sorted((p for p in folder.iterdir() if p.is_dir()), reverse=True):
        meta_path = batch / 'batch.json'
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        items.append({
            'id': meta.get('id') or batch.name,
            'source': meta.get('source') or '',
            'created': meta.get('created') or '',
            'status': meta.get('status') or '',
            'message': meta.get('message') or '',
            'stats': meta.get('stats') or {},
        })
        if len(items) >= limit:
            break
    return items
