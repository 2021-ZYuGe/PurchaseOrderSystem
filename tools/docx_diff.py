# -*- coding: utf-8 -*-
"""比较两份 .docx 的正文、表格与页眉页脚，用来确认改动前后生成结果一致。

用法：
    python tools/docx_diff.py old.docx new.docx        # 逐行 diff，有差异返回 1
    python tools/docx_diff.py --snapshot new.docx      # 只打印快照，便于存档

只比较文字和段落/表格顺序，不比较文件字节：docx 内含创建时间、作者等元数据，
直接比字节永远是"不一致"。
"""
import argparse
import difflib
import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def cell_text(cell):
    """单元格文字：多个段落用 / 连接，嵌套表格递归展开"""
    parts = []
    for paragraph in cell.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)
    for table in cell.tables:
        for row in table.rows:
            parts.append(' | '.join(cell_text(item) for item in row.cells))
    return ' / '.join(parts)


def iter_blocks(doc):
    """按正文真实顺序产出段落和表格（doc.paragraphs 会丢掉表格）"""
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            yield Paragraph(child, doc)
        elif tag == 'tbl':
            yield Table(child, doc)


def snapshot(path):
    """把整份文档摊平成可 diff 的纯文本"""
    doc = Document(str(path))
    lines = []
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.append('[P] ' + text)
            continue
        lines.append('[TBL]')
        for row in block.rows:
            lines.append('  [R] ' + ' | '.join(cell_text(cell) for cell in row.cells))
        lines.append('[/TBL]')

    for index, section in enumerate(doc.sections):
        for label, part in (('HEADER', section.header), ('FOOTER', section.footer)):
            texts = [p.text.strip() for p in part.paragraphs if p.text.strip()]
            if texts:
                lines.append('[%s%d] %s' % (label, index, ' / '.join(texts)))

    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description='比较两份 docx 的文字内容')
    parser.add_argument('old', type=Path, help='旧文件')
    parser.add_argument('new', nargs='?', type=Path, help='新文件')
    parser.add_argument('--snapshot', action='store_true',
                        help='只打印第一个文件的快照')
    args = parser.parse_args(argv)

    if not args.old.is_file():
        print('找不到文件：%s' % args.old, file=sys.stderr)
        return 2

    if args.snapshot or args.new is None:
        print('\n'.join(snapshot(args.old)))
        return 0

    if not args.new.is_file():
        print('找不到文件：%s' % args.new, file=sys.stderr)
        return 2

    old_lines = snapshot(args.old)
    new_lines = snapshot(args.new)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=str(args.old), tofile=str(args.new), lineterm=''))
    if not diff:
        print('内容一致')
        return 0

    print('\n'.join(diff))
    print('\n共 %d 行差异' % sum(1 for line in diff if line[:1] in '+-'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
