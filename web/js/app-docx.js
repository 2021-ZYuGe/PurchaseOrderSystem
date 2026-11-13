// docx
// 浏览器端 DOCX 生成（CRC/ZIP/图片内嵌），不依赖服务端。

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(u8) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
const _te = new TextEncoder();
const _u16 = n => [n & 0xFF, (n >>> 8) & 0xFF];
const _u32 = n => [n & 0xFF, (n >>> 8) & 0xFF, (n >>> 16) & 0xFF, (n >>> 24) & 0xFF];
const _cat = arrs => { let L = 0; arrs.forEach(a => L += a.length); const o = new Uint8Array(L); let p = 0; arrs.forEach(a => { o.set(a, p); p += a.length; }); return o; };
const esc = s => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/\u000B/g, " ");

function zipStore(files) {
  const locals = [], centrals = [];
  let off = 0;
  files.forEach(f => {
    const data = f.data, name = _te.encode(f.name);
    const crc = crc32(data);
    const lh = _cat([_u32(0x04034b50), _u16(20), _u16(0x0800), _u16(0), _u16(0), _u16(0),
      _u32(crc), _u32(data.length), _u32(data.length), _u16(name.length), _u16(0)]);
    locals.push(lh, name, data);
    centrals.push(_cat([_u32(0x02014b50), _u16(20), _u16(20), _u16(0x0800), _u16(0), _u16(0), _u16(0),
      _u32(crc), _u32(data.length), _u32(data.length), _u16(name.length), _u16(0), _u16(0),
      _u16(0), _u16(0), _u32(0), _u32(off)]), name);
    off += lh.length + name.length + data.length;
  });
  const cd = _cat(centrals);
  const eocd = _cat([_u32(0x06054b50), _u16(0), _u16(0), _u16(files.length), _u16(files.length), _u32(cd.length), _u32(off), _u16(0)]);
  return new Blob([_cat(locals), cd, eocd], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
}

class DocxBuilder {
  constructor() {
    this.paras = [];   // 正文段落（表格之前）
    this.paras2 = [];  // 表格之后的段落
    this.table = null;
    this.media = [];
  }
  _p(p) {
    const sz = p.size || 21, color = p.color ? `<w:color w:val="${p.color}"/>` : "";
    const jc = p.align ? `<w:jc w:val="${p.align}"/>` : "";
    const sp = `<w:spacing w:before="${p.spaceBefore || 40}" w:after="${p.spaceAfter || 80}" w:line="${p.line || 360}" w:lineRule="auto"/>`;
    return `<w:p><w:pPr>${sp}${jc}` +
      `<w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/>` +
      `<w:b w:val="${p.bold ? 1 : 0}"/><w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/>${color}</w:rPr>` +
      `</w:pPr><w:r><w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/>` +
      `<w:b w:val="${p.bold ? 1 : 0}"/><w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/>${color}</w:rPr>` +
      `<w:t xml:space="preserve">${esc(p.t)}</w:t></w:r></w:p>`;
  }
  _cell(c, w, alignFallback) {
    const align = c.align || alignFallback || "left";
    let body = "";
    if (c.image) {
      const idx = this.media.length;
      this.media.push({ b64: c.image, ext: c.ext || "png" });
      // wp:extent 用 EMU：1 twip = 635 EMU
      const cx = (c.wtwips || 1100) * 635, cy = (c.htwips || 1100) * 635;
      body = `<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="20" w:after="20"/></w:pPr><w:r><w:drawing>` +
        `<wp:inline distT="0" distB="0" distL="0" distR="0">` +
        `<wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="${idx + 1}" name="img${idx}"/>` +
        `<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">` +
        `<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
        `<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
        `<pic:nvPicPr><pic:cNvPr id="${idx}" name="img${idx}"/><pic:cNvPicPr/></pic:nvPicPr>` +
        `<pic:blipFill><a:blip r:embed="rIdImg${idx}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>` +
        `<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>` +
        `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>` +
        `</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>`;
    } else {
      const sz = c.bold ? 20 : 19;
      body = `<w:p><w:pPr><w:jc w:val="${align}"/><w:spacing w:before="30" w:after="30" w:line="260" w:lineRule="auto"/>` +
        `<w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/><w:b w:val="${c.bold ? 1 : 0}"/><w:sz w:val="${sz}"/></w:rPr></w:pPr>` +
        `<w:r><w:rPr><w:rFonts w:ascii="微软雅黑" w:eastAsia="微软雅黑" w:hAnsi="微软雅黑"/><w:b w:val="${c.bold ? 1 : 0}"/><w:sz w:val="${sz}"/>` +
        (c.color ? `<w:color w:val="${c.color}"/>` : "") + `</w:rPr>` +
        `<w:t xml:space="preserve">${esc(c.text)}</w:t></w:r></w:p>`;
    }
    const shd = c.shade ? `<w:shd w:val="clear" w:color="auto" w:fill="${c.shade}"/>` : "";
    const gs = c.gridSpan ? `<w:gridSpan w:val="${c.gridSpan}"/>` : "";
    return `<w:tc><w:tcPr><w:tcW w:w="${w}" w:type="dxa"/>${gs}${shd}` +
      `<w:vAlign w:val="center"/></w:tcPr>${body}</w:tc>`;
  }
  build() {
    const W = 9040;
    let grid = "", tbl = "";
    if (this.table) {
      grid = this.table.widths.map(w => `<w:gridCol w:w="${w}"/>`).join("");
      tbl = this.table.rows.map((r, ri) => {
        const cells = r.map((c, ci) => this._cell(c, this.table.widths[ci] || 1000, ri === 0 ? "center" : "left")).join("");
        return `<w:tr><w:trPr><w:trHeight w:val="1000" w:hRule="atLeast"/><w:jc w:val="center"/></w:trPr>${cells}</w:tr>`;
      }).join("");
    }
    const borders = `<w:tblBorders>` +
      ["top", "left", "bottom", "right", "insideH", "insideV"]
        .map(s => `<w:${s} w:val="single" w:sz="6" w:space="0" w:color="000000"/>`).join("") + `</w:tblBorders>`;

    const documentXml =
`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<w:body>
${this.paras.map(p => this._p(p)).join("")}
${this.table ? `<w:tbl><w:tblPr><w:tblW w:w="${W}" w:type="dxa"/><w:tblLayout w:type="fixed"/>${borders}<w:tblCellMar><w:left w:w="60" w:type="dxa"/><w:right w:w="60" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>${grid}</w:tblGrid>${tbl}</w:tbl>` : ""}
${this.paras2.map(p => this._p(p)).join("")}
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1247" w:right="1300" w:bottom="1247" w:left="1300" w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>
</w:body></w:document>`;

    const contentTypes =
`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Default Extension="jpg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`;

    const rootRels =
`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`;

    const docRels =
`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${this.media.map((m, i) => `<Relationship Id="rIdImg${i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/img${i}.${m.ext}"/>`).join("")}
</Relationships>`;

    const files = [
      { name: "[Content_Types].xml", data: _te.encode(contentTypes) },
      { name: "_rels/.rels", data: _te.encode(rootRels) },
      { name: "word/document.xml", data: _te.encode(documentXml) },
      { name: "word/_rels/document.xml.rels", data: _te.encode(docRels) },
    ];
    this.media.forEach((m, i) => {
      const bin = atob(m.b64), u8 = new Uint8Array(bin.length);
      for (let k = 0; k < bin.length; k++) u8[k] = bin.charCodeAt(k);
      files.push({ name: `word/media/img${i}.${m.ext}`, data: u8 });
    });
    return zipStore(files);
  }
}

// ============ 图片工具：把 web/图片/xx.png 读成 base64，用于内嵌进 docx ============
const imgCache = new Map();
function loadImgB64(file) {
  if (imgCache.has(file)) return imgCache.get(file);
  const p = new Promise(res => {
    const x = new XMLHttpRequest();
    x.open("GET", "图片/" + encodeURIComponent(file), true);
    x.responseType = "arraybuffer";
    x.onload = () => {
      if (x.status !== 200) return res(null);
      const b = new Uint8Array(x.responseBuffer || x.response);
      let s = "";
      const CH = 0x8000;
      for (let i = 0; i < b.length; i += CH) s += String.fromCharCode.apply(null, b.subarray(i, i + CH));
      res(btoa(s));
    };
    x.onerror = () => res(null);
    x.send();
  });
  imgCache.set(file, p);
  return p;
}

// 解析 PNG/JPEG 尺寸
function imgSize(b64) {
  try {
    const bin = atob(b64);
    const u8 = i => bin.charCodeAt(i);
    if (bin.charCodeAt(0) === 0x89 && bin.charCodeAt(1) === 0x50) {
      return { w: (u8(16)<<24)|(u8(17)<<16)|(u8(18)<<8)|u8(19), h: (u8(20)<<24)|(u8(21)<<16)|(u8(22)<<8)|u8(23), ext: "png" };
    }
    if (bin.charCodeAt(0) === 0xFF && bin.charCodeAt(1) === 0xD8) {
      let i = 2;
      while (i < bin.length - 9) {
        if (u8(i) !== 0xFF) { i++; continue; }
        const m = u8(i+1);
        const len = (u8(i+2)<<8) | u8(i+3);
        if (m >= 0xC0 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC) {
          return { h: (u8(i+5)<<8)|u8(i+6), w: (u8(i+7)<<8)|u8(i+8), ext: "jpeg" };
        }
        i += 2 + len;
      }
    }
  } catch (e) {}
  return { w: 300, h: 300, ext: "png" };
}

// ============ 重置 ============
function resetAll() {
  if (!confirm("确定清空当前订单？")) return;
  state = { supplier: null, items: [], pay: null };
  try { sessionStorage.removeItem("lastSupplier"); } catch (e) {}
  supInput.value = "";
  prodInput.value = "";
  supResults.classList.remove("show");
  prodResults.classList.remove("show");
  document.getElementById("supInfo").style.display = "none";
  hideContractBox();
  document.getElementById("cardProduct").style.display = "none";
  document.getElementById("cardPay").style.display = "none";
  document.getElementById("cardTotal").style.display = "none";
  payBox.querySelectorAll(".pay-opt").forEach(o => o.classList.remove("active"));
  renderItems();
}

// ============ 导出 Word（只出《产品订购清单》页）============
async function exportDoc() {
  if (!state.supplier) { alert("请先选择供应商"); return; }
  if (!state.items.length) { alert("请先添加产品"); return; }
  if (!state.pay) { alert("请选择付款方式"); return; }
  const t = grandTotal();
  const sup = state.supplier;
  const supplierName = sup ? sup.供应商名称 : "＿＿＿＿＿＿＿＿＿＿";
  const supplierTel = sup && sup.电话 ? sup.电话 : "＿＿＿＿＿＿＿＿";

  // 主合同日期：优先用档案里的最新签约日期
  let md = sup && sup.主合同日期 ? sup.主合同日期 : "";
  let mainDateTxt;
  if (md) {
    const p = md.split("-").map(Number);
    mainDateTxt = `【${p[0]}】年【${p[1]}】月【${p[2]}】日`;
  } else {
    mainDateTxt = `【      】年【     】月【     】日`;
  }

  // 备注统一取第一行非空的（一般全表一致），每行可单独改
  const remarkOf = it => (it.备注 || "").trim();

  let payText = "";
  if (state.pay === "full") {
    payText = `本产品订单总金额为${fmt(t)}元，签订本产品订购清单，并经甲乙双方确认当次甲方应付金额后，甲方应及时向乙方付款。乙方应在甲方支付全部款项后7个工作日内向甲方开具等额合法有效的13%增值税专用发票。`;
  } else if (state.pay === "p30") {
    payText = `本产品订单总金额为${fmt(t)}元，甲方签订合同后10个工作日内向乙方支付30%预付款，即${fmt(t*0.3)}元。乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，甲方收到通知后支付剩余尾款${fmt(t*0.7)}元。乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的13%增值税专用发票。`;
  } else {
    payText = `本产品订单总金额为${fmt(t)}元，甲方签订合同后10个工作日内向乙方支付50%预付款，即${fmt(t*0.5)}元。乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，甲方收到通知后支付剩余尾款${fmt(t*0.5)}元。乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的13%增值税专用发票。`;
  }

  const today = new Date();
  const dstr = `${today.getFullYear()}年${today.getMonth()+1}月${today.getDate()}日`;

  // ---- 预读所有图片为 base64（内嵌进 docx，避免运行时找不到路径）----
  const btn = document.getElementById("btnExport");
  const oldTxt = btn.textContent;
  btn.disabled = true;
  btn.textContent = "正在打包图片…";
  const b64List = await Promise.all(state.items.map(it => it.图片 ? loadImgB64(it.图片) : Promise.resolve(null)));
  btn.textContent = "正在生成 Word…";

  const doc = new DocxBuilder();
  doc.paras.push({ t: "产品订购清单", align: "center", bold: true, size: 32, spaceAfter: 240 });

  const info = [
    `购货单位（甲方）：广州兴趣岛信息科技有限公司`,
    `供货单位（乙方）：${supplierName}`,
    `交货地址：广州市花都区花都沿江大道24号永日电梯（昊运仓储公司）张生 17675625750`,
  ];
  info.forEach(s => doc.paras.push({ t: s, size: 21, line: 340 }));
  doc.paras.push({ t: "（送货记得打托，送货单：包含箱数，箱规，尾货散货做好标记）", size: 18, color: "666666", line: 340, spaceAfter: 160 });
  doc.paras.push({ t: `甲乙双方已于${mainDateTxt}签订了《购销框架合同》（以下简称“主合同”），现双方协商一致特签订本《产品订购清单》，乙方按以下表格内容及要求及时提供产品：`, size: 21, line: 340, spaceAfter: 160 });

  // ---- 表格（对标历史合同版式）：商品名称 / 商品图片 / 规格 / 数量（个）/ 单个价格 / 总金额 / 备注 ----
  const GREEN = "D9EAD3"; // 浅绿底，与历史合同一致
  const widths = [1700, 1300, 1500, 900, 1000, 1300, 1340]; // twips，合计 9040 ≈ A4正文宽
  const heads = ["商品名称", "商品图片", "规格", "数量（个）", "单个价格", "总金额", "备注"];
  doc.table = { widths, rows: [] };
  doc.table.rows.push(heads.map(h => ({ text: h, align: "center", bold: true, shade: GREEN })));

  // 按图片原始比例缩放进 1.7cm 见方区域内（twips = px * 15 @96dpi）
  state.items.forEach((it, i) => {
    const b64 = b64List[i];
    let imgCell;
    if (b64) {
      const sz = imgSize(b64);
      let wT = Math.min(1100, sz.w * 15);
      let hT = Math.round(wT * sz.h / sz.w);
      if (hT > 1100) { hT = 1100; wT = Math.round(hT * sz.w / sz.h); }
      imgCell = { image: b64, ext: sz.ext, wtwips: wT, htwips: hT };
    } else {
      imgCell = { text: "", align: "center" };
    }
    doc.table.rows.push([
      { text: it.产品名称, shade: GREEN },
      imgCell,
      { text: it.规格 || "", shade: GREEN },
      { text: it.数量 || "", align: "right", shade: GREEN },
      { text: `${fmt(parseFloat(it.单价) || 0)} 元`, align: "right", shade: GREEN },
      { text: `${fmt(itemAmount(it))} 元`, align: "right", shade: GREEN },
      { text: remarkOf(it), shade: GREEN },
    ]);
  });
  doc.table.rows.push([
    { text: "合计（含税）", align: "center", bold: true, gridSpan: 4, shade: GREEN },
    { text: `¥${fmt(t)} 元，除前述费用外，甲方无需支付其他费用，乙方应按甲方的要求提供货物。`, bold: true, gridSpan: 3, shade: GREEN },
  ]);

  const after = [
    { t: "1. 结算方式：" },
    { t: payText },
    { t: "2. 交货时间：乙方应在【2026】年【　】月【　】日前向甲方提供上述产品。" },
    { t: "3. 本《产品订购清单》作为双方已签订的主合同的一部分，与主合同约定不一致的，以本清单约定为准；本清单内未约定的事宜以双方签订的主合同为准。" },
    { t: "4. 本《产品订购清单》自双方盖章之日起生效，一式贰份，双方各执壹份，具有同等法律效力。" },
    { t: "（此行以下无正文）", size: 18, color: "666666", spaceAfter: 280 },
    { t: `甲方：广州兴趣岛信息科技有限公司　　　　乙方：${supplierName}`, spaceBefore: 200, spaceAfter: 240 },
    { t: "（盖章）　　　　　　　　　　　　　　　　（盖章）", spaceAfter: 240 },
    { t: `签署日期：${dstr}　　　　　　　　　　签署日期：${dstr}` },
  ];
  after.forEach(p => doc.paras2.push(Object.assign({ size: 21, line: 360 }, p)));

  const blob = doc.build();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const tag = md ? `_主合同${md.replace(/-/g,"")}` : "";
  a.download = `产品订购清单_${supplierName}_${dstr.replace(/\D/g,"")}${tag}.docx`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);

  btn.disabled = false;
  btn.textContent = oldTxt;
}

// ============ 一键导出《购销框架合同》主体（首次合作/需重签用）============
function exportMainContract() {
  const sup = state.supplier;
  const supplierName = sup ? sup.供应商名称 : "＿＿＿＿＿＿＿＿＿＿";
  const supplierTel = sup && sup.电话 ? sup.电话 : "＿＿＿＿＿＿＿＿";
  const today = new Date();
  const dstr = `${today.getFullYear()}年${today.getMonth()+1}月${today.getDate()}日`;
  // 合同期限止日 = 起算日 + 1 年 - 1 天（如 2026-11-04 起 → 2027-11-03 止）
  const endDate = new Date(today.getFullYear() + 1, today.getMonth(), today.getDate());
  endDate.setDate(endDate.getDate() - 1);
  const endYear = endDate.getFullYear();
  const endMonth = endDate.getMonth() + 1;
  const endDay = endDate.getDate();

  const doc = new DocxBuilder();
  const P = (t, o) => doc.paras.push(Object.assign({ t, size: 21, line: 340 }, o || {}));

  P("购销框架合同", { align: "center", bold: true, size: 32, spaceAfter: 240, line: 300 });
  P("甲方（购货方）：广州兴趣岛信息科技有限公司");
  P("乙方（供货方）：" + supplierName);
  P("根据《中华人民共和国民法典》及其有关法律法规，为明确甲乙双方的权利义务，甲、乙双方经友好协商，就乙方在合作期内为甲方供应产品，达成如下框架合同：", { spaceAfter: 200 });

  P("一、产品的供应", { bold: true });
  P("1、乙方向甲方供应产品的品种、数量、交货日期、交货地点及价格以附件的《产品订购清单》为准。甲方如有新的需求，可在本合同有效期限内与乙方继续签订《产品订购清单》。");
  P("2、乙方接到甲方的购买需求时，应另行准备一定的数量作为备用量，以便及时退换。", { spaceAfter: 160 });

  P("二、产品的质量与保证", { bold: true });
  P("1、乙方向甲方供应的产品的质量应当符合该产品的国家标准和行业标准，没有国家标准和行业标准的按照通常标准或符合合同目的的特定标准。");
  P("2、在乙方每次向甲方供应产品时，双方可在《产品订购清单》上对该产品的具体质量标准进行约定。乙方在向甲方交付产品的同时应当提交所供应产品合格证或质量保证书。");
  P("3、乙方应对其供应的产品质量负责，承担因其产品存在质量问题所引起的全部责任，并赔偿因此给甲方造成的全部损失。乙方保证产品质量保证期为【1】年，自甲方收到货物时起算。", { spaceAfter: 160 });

  P("三、供应产品的具体内容", { bold: true });
  P("供货方式采用乙方一次性发货，除非甲方要求乙方分开发货，发货的运费全部均由乙方承担，若甲方有特殊要求的，则由甲乙双方协商解决。", { spaceAfter: 160 });

  P("四、验收及标准", { bold: true });
  P("1、对于乙方供应的产品，甲方在验收时采用本合同第二条的约定及国家相关法律法规规定作为验收标准及退换货依据。");
  P("2、甲方在验收时，如发现产品不符合验收标准的，有权拒收不合格产品或要求乙方退换，乙方需在甲方要求后【3】日内如数补足或重新交付产品并经验收合格。", { spaceAfter: 160 });

  P("五、供应产品的退换货", { bold: true });
  P("1、乙方在任何时候须保证无条件退换不符合本合同约定及/或甲方要求的产品或者存在质量问题的产品。");
  P("2、因乙方产品质量问题或非甲方原因导致的退换货，产生的全部运费及其他相关费用均由乙方负责。", { spaceAfter: 160 });

  P("六、结算方式", { bold: true });
  P(`1、甲方以银行转账的方式向乙方支付相应款项，具体的结算方式以双方另行签订的《产品订购清单》约定为准。订单总金额低于人民币${fmt0(PAY_THRESHOLD)}元的适用全额付款；达到${fmt0(PAY_THRESHOLD)}元及以上的，可选择30%或50%预付款方式。`);
  P("2、乙方保证向甲方提供的发票为合法有效的。乙方应在收到货款后【15】个工作日内向甲方开具等额合法有效的税率为【13%】的增值税专用发票。");
  P("3、乙方收款账户信息：");
  P("开户名称：" + supplierName);
  P("账　　号：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿");
  P("开户行：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿", { spaceAfter: 160 });

  P("七、双方权利义务", { bold: true });
  P("1、乙方应当保证其为所供应产品的品牌方，有权授权甲方在线上或线下售卖或赠送本协议项下的产品，保证其所供应的产品及推广素材符合国家相关法律法规的要求，不存在任何知识产权的瑕疵。");
  P("2、双方在合作过程中获知的对方的商业秘密、订购信息等保密信息，在任何时候均不得向第三方披露或公开。", { spaceAfter: 160 });

  P("八、违约责任", { bold: true });
  P("1、任何一方没有充分、及时履行义务的，应当承担违约责任，赔偿给对方造成的全部损失。");
  P("2、乙方逾期发货的，每逾期一天按逾期发货产品总价的1%计算违约金。乙方逾期超过7天的，甲方有权取消本订单。");
  P("3、乙方不得向甲方员工、顾问等相关团队人员提供任何形式的不正当利益（款项或实物金额超过200元），否则甲方有权单方解除本协议且不承担任何违约责任。", { spaceAfter: 160 });

  P("九、争议及诉讼管辖", { bold: true });
  P("甲乙双方因履行本合同发生争议的，应友好协商解决；协商不成的，双方同意由甲方所在地人民法院管辖。", { spaceAfter: 160 });

  P("十、其他", { bold: true });
  P(`1、本合同期限为【壹】年，自【${today.getFullYear()}】年【${today.getMonth()+1}】月【${today.getDate()}】日起至【${endYear}】年【${endMonth}】月【${endDay}】日止。`);
  P("2、本合同自双方盖章之日起生效，一式贰份，甲乙双方各执壹份，具有同等法律效力。");
  P("3、本合同附件《产品订购清单》作为本合同的一部分，与本合同具有同等法律效力。", { spaceAfter: 320 });

  P(`甲方（盖章）：广州兴趣岛信息科技有限公司　　　　乙方（盖章）：${supplierName}`);
  P("法定代表人（签字/盖章）：　　　　　　　　　　　法定代表人（签字/盖章）：");
  P(`乙方联系电话：${supplierTel}`);
  P(`签署日期：${dstr}　　　　　　　　　　签署日期：${dstr}`, { spaceBefore: 160 });

  const a = document.createElement("a");
  a.href = URL.createObjectURL(doc.build());
  a.download = `购销框架合同_${supplierName}_${dstr.replace(/\D/g,"")}.docx`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}

