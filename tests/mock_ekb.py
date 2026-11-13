# -*- coding: utf-8 -*-
"""本地模拟易快报接口，用于集成测试（不访问真实服务、不需要 accessToken）。

提供与真实接口同形的：
  GET  /api/account/v2/session
  GET  /api/v1/organization/staffs/me
  POST /api/flow/v1/flows/my
  POST /api/flow/v1/flows/flowId/$<id>
  POST /api/v1/attachment/attachments/ids
  GET  /download/<fileId>
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DOCS = [
    ROOT / 'tests' / 'golden' / 'simple' / 'contract.docx',
    ROOT / 'tests' / 'golden' / 'dropship' / 'contract.docx',
]

TOKEN = 'accept-token-9f3a'
BILLS = [
    {'flow': {'id': 'f1', 'state': 'completed'},
     'form': {'specification': {'name': '合同审批流程'}, 'code': 'S99990001',
              'title': '验收测试合同一', 'submitDate': 1794550000000}},
    {'flow': {'id': 'f2', 'state': 'paid'},
     'form': {'specification': {'name': '合同审批流程'}, 'code': 'S99990002',
              'title': '验收测试合同二', 'submitDate': 1794550000000}},
]
FILES = {
    'f1': [{'fileId': 'a1', 'fileName': '采购合同-1793862012472-723.docx', 'blob': 0},
           {'fileId': 'a2', 'fileName': '报价单.pdf', 'blob': None}],
    'f2': [{'fileId': 'b1', 'fileName': '采购合同-1793862012473-724.docx', 'blob': 1}],
}


class MockEkb:
    def __init__(self, token=TOKEN):
        self.token = token
        self.docs = [p.read_bytes() for p in SAMPLE_DOCS]
        self.downloads = []
        self.calls = []
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self):
        return 'http://127.0.0.1:%d' % self.port

    def link(self, token=None):
        return '%s/client/x?accessToken=%s&ekbCorpId=demo' % (self.base, token or self.token)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _handler(mock):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, obj, status=200):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get('Content-Length') or 0)
                return json.loads(self.rfile.read(n).decode() or '{}') if n else {}

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                mock.calls.append(('GET', parsed.path))
                if parsed.path == '/api/account/v2/session':
                    if query.get('accessToken', [''])[0] != mock.token:
                        return self._json({'error': 'bad token'}, 401)
                    return self._json({'value': {'userId': 'u1'}})
                if parsed.path == '/api/v1/organization/staffs/me':
                    return self._json({'value': {'staff': {'name': '验收测试员'}}})
                if parsed.path.startswith('/download/'):
                    file_id = parsed.path.rsplit('/', 1)[-1]
                    mock.downloads.append({'id': file_id, 'headers': dict(self.headers)})
                    blob = None
                    for files in FILES.values():
                        for item in files:
                            if item['fileId'] == file_id:
                                blob = item['blob']
                    data = b'%PDF-1.4 fake' if blob is None else mock.docs[blob]
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._json({'error': 'not found'}, 404)

            def do_POST(self):
                parsed = urlparse(self.path)
                mock.calls.append(('POST', parsed.path))
                body = self._body()
                if parsed.path == '/api/flow/v1/flows/my':
                    return self._json({'count': len(BILLS), 'items': BILLS})
                if parsed.path.startswith('/api/flow/v1/flows/flowId/$'):
                    flow_id = parsed.path.rsplit('$', 1)[-1]
                    return self._json({'value': {'form': {
                        'specification': {'name': '合同审批流程'},
                        'attachments': FILES.get(flow_id, []),
                    }}})
                if parsed.path == '/api/v1/attachment/attachments/ids':
                    ids = body.get('ids') or []
                    return self._json({'items': [
                        {'id': i, 'url': '%s/download/%s' % (mock.base, i)} for i in ids
                    ]})
                self._json({'error': 'not found'}, 404)

        return Handler
