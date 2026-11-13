# -*- coding: utf-8 -*-
"""把 .docx 摊平成可 diff 的纯文本快照。

只比文字和表格结构，不比二进制：docx 里带创建时间、作者等元数据，
直接比文件字节永远是"不一致"。文字一致 + 段落/表格顺序一致，
就足以证明模板填充逻辑没被改坏。
"""
from docx.table import Table
from docx.text.paragraph import Paragraph


def _cell_text(cell):
    """单元格文字：多个段落用 / 连接，嵌套表格递归展开"""
    parts = []
    for p in cell.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)
    for tb in cell.tables:
        for row in tb.rows:
            parts.append(' | '.join(_cell_text(c) for c in row.cells))
    return ' / '.join(parts)


def iter_blocks(doc):
    """按正文真实顺序产出段落和表格（python-docx 的 doc.paragraphs 会丢掉表格）"""
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            yield Paragraph(child, doc)
        elif tag == 'tbl':
            yield Table(child, doc)


def snapshot(doc):
    lines = []
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.append('[P] ' + text)
            continue
        lines.append('[TBL]')
        for row in block.rows:
            lines.append('  [R] ' + ' | '.join(_cell_text(c) for c in row.cells))
        lines.append('[/TBL]')

    for idx, section in enumerate(doc.sections):
        for label, part in (('HEADER', section.header), ('FOOTER', section.footer)):
            texts = [p.text.strip() for p in part.paragraphs if p.text.strip()]
            if texts:
                lines.append('[%s%d] %s' % (label, idx, ' / '.join(texts)))

    return '\n'.join(lines) + '\n'
