# -*- coding: utf-8 -*-
"""易快报 HTTP 链路集成测试：用本地模拟服务跑通真实 urllib 请求。

不访问外网、不需要 accessToken，但走完整的 会话 → 列表 → 详情 → 解析直链 → 下载。
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for path in (HERE, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.integrations import ekuaibao
from mock_ekb import MockEkb


class HttpLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = MockEkb().start()
        cls.base, cls.corp, cls.token = ekuaibao.parse_link(cls.mock.link())

    @classmethod
    def tearDownClass(cls):
        cls.mock.stop()

    def client(self, token=None):
        return ekuaibao.Ekb(
            self.base, self.corp, token or self.token,
            transport=ekuaibao.UrllibTransport(),
            throttle=ekuaibao.Throttle(base=0))

    def test_session_and_staff(self):
        client = self.client()
        self.assertTrue(client.open_session())
        self.assertEqual(client.who_am_i(), '验收测试员')

    def test_bad_token(self):
        client = self.client(token='bad-token')
        with self.assertRaises(ekuaibao.AuthError):
            client.open_session()

    def test_list_and_select(self):
        client = self.client()
        items = client.list_bills()
        self.assertEqual(len(items), 2)
        targets = ekuaibao.select_targets(items, template='合同审批流程')
        self.assertEqual([t['code'] for t in targets], ['S99990001', 'S99990002'])

    def test_detail_resolve_download(self):
        client = self.client()
        detail = client.bill_detail('f1')
        fields = []
        ekuaibao.collect_file_fields(detail.get('form') or {}, fields)
        self.assertEqual(len(fields), 2)
        names = [ekuaibao.strip_suffix(f['fileName']) for f in fields]
        self.assertIn('采购合同.docx', names, '内部后缀应被去掉')

        links = client.resolve_files(['a1', 'b1'])
        self.assertIn('a1', links)
        self.assertTrue(links['a1']['url'].startswith(self.mock.base + '/download/'))

        folder = Path(tempfile.mkdtemp(prefix='ekb_'))
        try:
            target = folder / 'x.docx'
            size = client.download(links['a1']['url'], str(target), timeout=10)
            self.assertEqual(size, len(self.mock.docs[0]))
            self.assertEqual(target.read_bytes(), self.mock.docs[0])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

        # 签名直链不能带会话头，否则 OSS 会 403
        headers = {k.lower() for k in self.mock.downloads[-1]['headers']}
        for forbidden in ('accesstoken', 'corpid', 'content-type'):
            self.assertNotIn(forbidden, headers)


if __name__ == '__main__':
    unittest.main(verbosity=2)
