// 浏览器端 DOCX 生成（CRC/ZIP/图片内嵌），不依赖服务端。
// 由 web/js/app-docx.js 移植为 ES module，生成逻辑保持原样。

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()

function crc32(u8) {
  let c = 0xffffffff
  for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

const _te = new TextEncoder()
const _u16 = (n) => [n & 0xff, (n >>> 8) & 0xff]
const _u32 = (n) => [n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff]
const _cat = (arrs) => {
  let L = 0
  arrs.forEach((a) => (L += a.length))
  const o = new Uint8Array(L)
  let p = 0
  arrs.forEach((a) => {
    o.set(a, p)
    p += a.length
  })
  return o
}
const esc = (s) =>
  String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/\u000B/g, ' ')

function zipStore(files) {
  const locals = []
  const centrals = []
  let off = 0
  files.forEach((f) => {
    const data = f.data
    const name = _te.encode(f.name)
    const crc = crc32(data)
    const lh = _cat([
      _u32(0x04034b50),
      _u16(20),
      _u16(0x0800),
      _u16(0),
      _u16(0),
      _u16(0),
      _u32(crc),
      _u32(data.length),
      _u32(data.length),
      _u16(name.length),
      _u16(0),
    ])
    locals.push(lh, name, data)
    centrals.push(
      _cat([
        _u32(0x02014b50),
        _u16(20),
        _u16(20),
        _u16(0x0800),
        _u16(0),
        _u16(0),
        _u16(0),
        _u32(crc),
        _u32(data.length),
        _u32(data.length),
        _u16(name.length),
        _u16(0),
        _u16(0),
        _u16(0),
        _u16(0),
        _u32(0),
        _u32(off),
      ]),
      name,
    )
    off += lh.length + name.length + data.length
  })
  const cd = _cat(centrals)
  const eocd = _cat([
    _u32(0x06054b50),
    _u16(0),
    _u16(0),
    _u16(files.length),
    _u16(files.length),
    _u32(cd.length),
    _u32(off),
    _u16(0),
  ])
  return new Blob([_cat(locals), cd, eocd], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
}

class DocxBuilder {
  constructor() {
    this.paras = [] // 正文段落（表格之前）
    this.paras2 = [] // 表格之后的段落
    this.table = null
    this.media = []
  }

  _p(p) {
    const sz = p.size || 21
    const color = p.color ? `<w:color w:val="${p.color}"/>` : ''
    const jc = p.align ? `<w:jc w:val="${p.align}"/>` : ''
    const sp = `<w:spacing w:before="${p.spaceBefore || 40}" w:after="${p.spaceAfter || 80}" w:line="${p.line || 360}" w:lineRule="auto"/>`
    return (
      `<w:p><w:pPr>${sp}${jc}` +
      `<w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/>` +
      `<w:b w:val="${p.bold ? 1 : 0}"/><w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/>${color}</w:rPr>` +
      `</w:pPr><w:r><w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/>` +
      `<w:b w:val="${p.bold ? 1 : 0}"/><w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/>${color}</w:rPr>` +
      `<w:t xml:space="preserve">${esc(p.t)}</w:t></w:r></w:p>`
    )
  }

  _cell(c, w, alignFallback) {
    const align = c.align || alignFallback || 'left'
    let body = ''
    if (c.image) {
      const idx = this.media.length
      this.media.push({ b64: c.image, ext: c.ext || 'png' })
      // wp:extent 用 EMU：1 twip = 635 EMU
      const cx = (c.wtwips || 1100) * 635
      const cy = (c.htwips || 1100) * 635
      body =
        `<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="20" w:after="20"/></w:pPr><w:r><w:drawing>` +
        `<wp:inline distT="0" distB="0" distL="0" distR="0">` +
        `<wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="${idx + 1}" name="img${idx}"/>` +
        `<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">` +
        `<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
        `<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
        `<pic:nvPicPr><pic:cNvPr id="${idx}" name="img${idx}"/><pic:cNvPicPr/></pic:nvPicPr>` +
        `<pic:blipFill><a:blip r:embed="rIdImg${idx}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>` +
        `<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>` +
        `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>` +
        `</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>`
    } else {
      const sz = c.bold ? 20 : 19
      body =
        `<w:p><w:pPr><w:jc w:val="${align}"/><w:spacing w:before="30" w:after="30" w:line="260" w:lineRule="auto"/>` +
        `<w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/><w:b w:val="${c.bold ? 1 : 0}"/><w:sz w:val="${sz}"/></w:rPr></w:pPr>` +
        `<w:r><w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/><w:b w:val="${c.bold ? 1 : 0}"/><w:sz w:val="${sz}"/>` +
        (c.color ? `<w:color w:val="${c.color}"/>` : '') +
        `</w:rPr>` +
        `<w:t xml:space="preserve">${esc(c.text)}</w:t></w:r></w:p>`
    }
    const shd = c.shade ? `<w:shd w:val="clear" w:color="auto" w:fill="${c.shade}"/>` : ''
    const gs = c.gridSpan ? `<w:gridSpan w:val="${c.gridSpan}"/>` : ''
    return (
      `<w:tc><w:tcPr><w:tcW w:w="${w}" w:type="dxa"/>${gs}${shd}` +
      `<w:vAlign w:val="center"/></w:tcPr>${body}</w:tc>`
    )
  }

  build() {
    const W = 9040
    let grid = ''
    let tbl = ''
    if (this.table) {
      grid = this.table.widths.map((w) => `<w:gridCol w:w="${w}"/>`).join('')
      tbl = this.table.rows
        .map((r, ri) => {
          const cells = r
            .map((c, ci) => this._cell(c, this.table.widths[ci] || 1000, ri === 0 ? 'center' : 'left'))
            .join('')
          return `<w:tr><w:trPr><w:trHeight w:val="1000" w:hRule="atLeast"/><w:jc w:val="center"/></w:trPr>${cells}</w:tr>`
        })
        .join('')
    }
    const borders =
      `<w:tblBorders>` +
      ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']
        .map((s) => `<w:${s} w:val="single" w:sz="6" w:space="0" w:color="000000"/>`)
        .join('') +
      `</w:tblBorders>`

    const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<w:body>
${this.paras.map((p) => this._p(p)).join('')}
${this.table ? `<w:tbl><w:tblPr><w:tblW w:w="${W}" w:type="dxa"/><w:tblLayout w:type="fixed"/>${borders}<w:tblCellMar><w:left w:w="60" w:type="dxa"/><w:right w:w="60" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>${grid}</w:tblGrid>${tbl}</w:tbl>` : ''}
${this.paras2.map((p) => this._p(p)).join('')}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1247" w:right="1300" w:bottom="1247" w:left="1300" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>
</w:body></w:document>`

    const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Default Extension="jpg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`

    const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`

    const docRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${this.media.map((m, i) => `<Relationship Id="rIdImg${i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/img${i}.${m.ext}"/>`).join('')}
</Relationships>`

    const files = [
      { name: '[Content_Types].xml', data: _te.encode(contentTypes) },
      { name: '_rels/.rels', data: _te.encode(rootRels) },
      { name: 'word/document.xml', data: _te.encode(documentXml) },
      { name: 'word/_rels/document.xml.rels', data: _te.encode(docRels) },
    ]
    this.media.forEach((m, i) => {
      const bin = atob(m.b64)
      const u8 = new Uint8Array(bin.length)
      for (let k = 0; k < bin.length; k++) u8[k] = bin.charCodeAt(k)
      files.push({ name: `word/media/img${i}.${m.ext}`, data: u8 })
    })
    return zipStore(files)
  }
}

export { DocxBuilder, zipStore }
