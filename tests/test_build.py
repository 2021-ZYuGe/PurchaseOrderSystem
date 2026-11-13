# -*- coding: utf-8 -*-
"""发布包构建：必须包含程序与模板，绝不能包含 data/、图片缓存和历史合同。"""
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable


class BuildReleaseTests(unittest.TestCase):
    def test_build_without_runtime(self):
        out = Path(tempfile.mkdtemp(prefix='release_'))
        try:
            result = subprocess.run(
                [PY, str(ROOT / '工具' / '构建发布包.py'), '--no-runtime', '--out', str(out)],
                cwd=str(ROOT), capture_output=True, timeout=180)
            output = result.stdout.decode('utf-8', 'replace')
            self.assertEqual(result.returncode, 0, output + result.stderr.decode('utf-8', 'replace'))

            zips = list(out.glob('*.zip'))
            self.assertEqual(len(zips), 1)
            with zipfile.ZipFile(zips[0]) as zf:
                raw = zf.namelist()
            tops = {n.split('/', 1)[0] for n in raw if '/' in n}
            prefix = next(iter(tops)) + '/' if len(tops) == 1 else ''
            names = [n[len(prefix):] for n in raw]
            self.assertFalse(any(n.startswith('data/') for n in names), '发布包不应包含 data/')
            self.assertFalse(any('图片/' in n for n in names), '发布包不应包含 web/图片')
            self.assertFalse(any('_生成合同/' in n for n in names), '发布包不应包含生成合同')
            self.assertFalse(any('__pycache__' in n for n in names))
            for must in ('app/config.py', 'web/index.html', 'web/welcome.html',
                         'web/js/app-main.js', 'version.json', '首次使用.txt'):
                self.assertIn(must, names)
        finally:
            import shutil
            shutil.rmtree(out, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
