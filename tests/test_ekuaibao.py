# -*- coding: utf-8 -*-
"""易快报客户端与预览逻辑（用假传输层，不访问真实接口）。"""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for path in (HERE, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import _loader
from app.integrations import ekuaibao as ekb


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, method, url, headers=None, body=None, timeout=60):
        self.calls.append((method, url))
        path = urlparse(url).path
        value = self.responses.get(path)
        if value is None:
            return 404, {}, b'{}'
        if isinstance(value, tuple):
            return value
        return 200, {}, json.dumps(value).encode('utf-8')

    def download(self, url, path, timeout=120):
        Path(path).write_bytes(b'fake-docx-content')
        return 17


class ParseLinkTests(unittest.TestCase):
    def test_full_link(self):
        url = ('https://wx2.ekuaibao.com/client/abc/#/workspace?accessToken=t0k&ekbCorpId=corp1')
        base, corp, token = ekb.parse_link(url)
        self.assertEqual(base, 'https://wx2.ekuaibao.com')
        self.assertEqual(corp, 'corp1')
        self.assertEqual(token, 't0k')

    def test_lowercase_and_default(self):
        base, corp, token = ekb.parse_link('https://x.ekuaibao.com/a?accesstoken=z&corpId=c')
        self.assertEqual((corp, token), ('c', 'z'))
        base, _, _ = ekb.parse_link('not a url')
        self.assertEqual(base, 'https://wx2.ekuaibao.com')

    def test_name_helpers(self):
        self.assertEqual(ekb.strip_suffix('合同-1793862012472-723.docx'), '合同.docx')
        self.assertEqual(ekb.safe_name('a/b:c*d.docx'), 'a_b_c_d.docx')


class ClientTests(unittest.TestCase):
    def make(self):
        transport = FakeTransport({
            '/api/account/v2/session': {'value': {'userId': 'u1'}},
            '/api/v1/organization/staffs/me': {'value': {'staff': {'name': '测试员'}}},
            '/api/flow/v1/flows/my': {'count': 2, 'items': [
                {'flow': {'id': 'f1', 'state': 'completed'},
                 'form': {'code': 'S1', 'title': 'A', 'submitDate': 1710000000000}},
                {'flow': {'id': 'f2', 'state': 'approving'},
                 'form': {'code': 'S2', 'title': 'B', 'submitDate': 1710000000000}},
            ]},
        })
        return ekb.Ekb('https://e.test', 'corp', 'tok', transport=transport), transport

    def test_session_and_name(self):
        client, _ = self.make()
        self.assertTrue(client.open_session())
        self.assertEqual(client.who_am_i(), '测试员')

    def test_list_bills(self):
        client, _ = self.make()
        items = client.list_bills()
        self.assertEqual(len(items), 2)
        self.assertEqual(client.last_total, 2)

    def test_auth_error(self):
        transport = FakeTransport({'/api/account/v2/session': (401, {}, b'{}')})
        client = ekb.Ekb('https://e.test', 'corp', 'tok', transport=transport)
        with self.assertRaises(ekb.AuthError):
            client.open_session()


class SelectTargetsTests(unittest.TestCase):
    def items(self):
        def one(fid, name, code, day, state='completed'):
            return {'flow': {'id': fid, 'state': state},
                    'form': {'specification': {'name': name}, 'code': code,
                             'title': code + '标题',
                             'submitDate': int(datetime.strptime(day, '%Y-%m-%d')
                                               .timestamp() * 1000)}}
        return [one('f1', '合同审批流程', 'S1', '2026-01-01'),
                one('f2', '合同审批流程', 'S2', '2026-06-01'),
                one('f3', '其他模板', 'S3', '2026-06-01')]

    def test_template_filter(self):
        got = ekb.select_targets(self.items())
        self.assertEqual([t['code'] for t in got], ['S1', 'S2'])

    def test_since_limit_codes(self):
        self.assertEqual([t['code'] for t in ekb.select_targets(self.items(), since='2026-05-01')], ['S2'])
        self.assertEqual([t['code'] for t in ekb.select_targets(self.items(), limit=1)], ['S1'])
        self.assertEqual([t['code'] for t in ekb.select_targets(self.items(), codes='s2')], ['S2'])

    def test_file_fields(self):
        acc = []
        ekb.collect_file_fields({'a': {'fileId': '1', 'fileName': 'x-1793862012472-1.docx'},
                                 'b': [{'fileId': '2', 'name': 'y.pdf'}]}, acc)
        self.assertEqual(len(acc), 2)


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = _loader.store()
        if not cls.store.product_count():
            raise unittest.SkipTest('没有数据')
        cls.known = sorted(cls.store.known_contract_numbers())[0]

    def test_preview_counts_new_and_duplicate(self):
        from app.services import imports
        known_code = self.known

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def open_session(self):
                return True

            def who_am_i(self):
                return '测试员'

            def list_bills(self, filter_by=None):
                return [
                    {'flow': {'id': 'f1', 'state': 'completed'},
                     'form': {'specification': {'name': '合同审批流程'},
                              'code': 'S99999999', 'title': '新合同',
                              'submitDate': 1794550000000}},
                    {'flow': {'id': 'f2', 'state': 'completed'},
                     'form': {'specification': {'name': '合同审批流程'},
                              'code': known_code, 'title': '老合同',
                              'submitDate': 1794550000000}},
                ]

        url = 'https://wx2.ekuaibao.com/x?accessToken=t&ekbCorpId=c'
        with mock.patch.object(imports.ekuaibao, 'Ekb', FakeClient):
            result = imports.preview_ekb({'url': url})
        self.assertTrue(result['ok'], result)
        data = result['data']
        self.assertEqual(data['matching'], 2)
        self.assertEqual(data['new'], 1)
        self.assertEqual(data['duplicates'], 1)
        self.assertEqual(data['who'], '测试员')

    def test_preview_rejects_bad_link(self):
        from app.services import imports
        result = imports.preview_ekb({'url': ''})
        self.assertFalse(result['ok'])
        result = imports.preview_ekb({'url': 'https://x/y'})
        self.assertFalse(result['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
