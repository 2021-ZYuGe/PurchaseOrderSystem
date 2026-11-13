# -*- coding: utf-8 -*-
"""生成《供应商信息缺口表》——谁的信息还缺，缺什么，去找谁要"""
import io
import os
import sys

import sqlite_store

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
ARCHIVE = str(sqlite_store.DB_PATH)
OUT = os.path.join(os.path.expanduser('~'), 'Desktop', '待补资料-供应商清单.xlsx')

# 生成合同时必需 / 强烈建议有的字段
# SQLite 数据层返回中文字段；这里是 显示名 -> 档案真实键
NEED = [
    ('统一社会信用代码', '统一社会信用代码', True),
    ('联系人', '联系人', True),
    ('联系电话', '电话', True),
    ('联系邮箱', '邮箱', True),
    ('联系地址', '地址', True),
    ('对公账号', '对公账号', True),
    ('开户行', '开户行', True),
    ('开户名称', '对公账户名', True),
    ('法定代表人', '法定代表人', False),
    ('微信号', '微信号', False),
]
# 页面硬性拦截的三项：没有就真的出不了合同
CORE = ['联系地址', '对公账号', '开户行']
OPTIONAL = {'微信号', '法定代表人'}

# 甲方自己的主体，不能算供应商
SELF_HINT = ('兴趣岛', 'qlchat', '千聊')

# 显示名 -> JSON 真实键
NEED_KEY = {
    '统一社会信用代码': '统一社会信用代码', '联系人': '联系人', '联系电话': '电话',
    '联系邮箱': '邮箱', '联系地址': '地址', '对公账号': '对公账号', '开户行': '开户行',
    '开户名称': '对公账户名', '法定代表人': '法定代表人', '微信号': '微信号',
}


def main():
    sqlite_store.ensure_database()
    sup = sqlite_store.list_supplier_profiles()
    # 剔除误抓进来的甲方主体
    sup = [s for s in sup
           if not any(h in (s.get('名称') or '') for h in SELF_HINT)]

    rows_ready, rows_block, rows_partial = [], [], []
    for s in sup:
        miss = [cn for cn, key, _req in NEED if not (s.get(key) or '').strip()]
        miss_core = [cn for cn in CORE if not (s.get(NEED_KEY[cn]) or '').strip()]
        # 开户名称默认就是公司全称，不算缺
        if '开户名称' in miss and (s.get('名称') or '').strip():
            miss.remove('开户名称')
        row = {
            '公司全称': s.get('名称', ''),
            '缺什么': '、'.join(miss) or '（齐全）',
            '联系人': s.get('联系人', ''),
            '联系电话': s.get('电话', ''),
            '联系邮箱': s.get('邮箱', ''),
            '还缺几项必填': len(miss_core),
            '最近签约': s.get('最近签署日期', ''),
        }
        if miss_core:
            rows_block.append(row)
        elif miss:
            rows_partial.append(row)
        else:
            rows_ready.append(row)

    rows_block.sort(key=lambda r: (-r['还缺几项必填'], r['公司全称']))
    rows_partial.sort(key=lambda r: r['公司全称'])
    rows_ready.sort(key=lambda r: r['公司全称'])

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        print('缺少 openpyxl，改为输出 CSV')
        import csv
        with open(OUT.replace('.xlsx', '.csv'), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['公司全称', '缺什么', '联系人', '联系电话', '联系邮箱', '还缺几项必填', '最近签约'])
            w.writeheader()
            for r in rows_block + rows_partial + rows_ready:
                w.writerow(r)
        return

    wb = Workbook()
    head_font = Font(bold=True, color='FFFFFF', size=11)
    head_fill = PatternFill('solid', fgColor='2B6CB0')
    warn_fill = PatternFill('solid', fgColor='FED7D7')
    ok_fill = PatternFill('solid', fgColor='C6F6D5')

    def sheet(name, rows, note):
        ws = wb.create_sheet(name)
        ws.append([note])
        ws['A1'].font = Font(bold=True, size=12, color='2B6CB0')
        ws.append([])
        cols = ['公司全称', '缺什么', '还缺几项必填', '联系人', '联系电话', '联系邮箱', '最近签约']
        ws.append(cols)
        for c in range(1, len(cols) + 1):
            cell = ws.cell(row=3, column=c)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
        for r in rows:
            ws.append([r.get(c, '') for c in cols])
        # 宽度 + 染色
        widths = [40, 34, 12, 12, 16, 26, 13]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for rr in range(4, 4 + len(rows)):
            if name.startswith("①"):
                ws.cell(row=rr, column=2).fill = warn_fill
            elif name.startswith("③"):
                ws.cell(row=rr, column=2).fill = ok_fill
        ws.freeze_panes = 'A4'
        return ws

    sheet('①没法出合同·必须催', rows_block,
          '缺「联系地址/对公账号/开户行」任一项 → 页面会拦住，生成不了合同。建议先用「导出信息收集表」发给对方要')
    sheet('②能出合同·建议补', rows_partial,
          '核心三项都有，可以直接出合同；下面这些填上会更完整（信用代码影响开票）')
    sheet('③资料齐全', rows_ready, '搜名字就能一键出合同，什么都不用补')

    # 汇总写在最前面
    ws0 = wb.create_sheet('汇总', 0)
    ws0.append(['供应商资料缺口汇总'])
    ws0['A1'].font = Font(bold=True, size=14, color='2B6CB0')
    ws0.append([])
    for line in [
        ['供应商总数', len(sup)],
        ['① 缺核心项，必须催', len(rows_block)],
        ['② 能出合同，建议补', len(rows_partial)],
        ['③ 资料齐全可直接用', len(rows_ready)],
        ['', ''],
        ['说明', '「核心项」指联系地址、对公账号、开户行 —— 缺任一项页面会拦住'],
        ['用法', '① 里的公司，先在合同页搜名字 → 导出信息收集表 → 发给对方填'],
    ]:
        ws0.append(line)
    ws0.column_dimensions['A'].width = 26
    ws0.column_dimensions['B'].width = 60
    for r in range(3, 11):
        ws0.cell(row=r, column=1).font = Font(bold=True)
    ws0['B8'].font = Font(color='C0392B', bold=True)

    del wb['Sheet']
    wb.save(OUT)

    print('=' * 60)
    print('供应商档案总数: %d' % len(sup))
    print('① 缺必填、必须先催 : %d 家' % len(rows_block))
    print('② 能出合同、建议补 : %d 家' % len(rows_partial))
    print('③ 资料齐全可直接用 : %d 家' % len(rows_ready))
    print('已导出: %s' % OUT)
    print()
    print('--- ① 里最急需的前 12 家 ---')
    for r in rows_block[:12]:
        print('  %-30s 缺 %d 项: %s' % (r['公司全称'][:30], r['还缺几项必填'], r['缺什么'][:44]))


if __name__ == '__main__':
    main()
