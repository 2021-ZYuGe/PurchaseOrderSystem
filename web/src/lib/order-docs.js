// 下单页在浏览器端生成 docx：产品订购清单 / 购销框架合同主体。
// 版式与 web/js/app-docx.js 保持一致，图片以 base64 内嵌。
import { DocxBuilder } from './docx'
import { dateDigits, formatCents, formatMoney, formatMoney0, inputToCents, mediaUrl } from './format'

export const DEFAULT_REMARK = '以上价格含13%专票+运费'

const GREEN = 'D9EAD3'
const imageCache = new Map()

export async function loadImageB64(file) {
  const url = mediaUrl(file)
  if (!url) return null
  if (imageCache.has(url)) return imageCache.get(url)
  const task = (async () => {
    try {
      const resp = await fetch(url, { cache: 'force-cache' })
      if (!resp.ok) return null
      const bytes = new Uint8Array(await resp.arrayBuffer())
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
      }
      return btoa(bin)
    } catch (e) {
      return null
    }
  })()
  imageCache.set(url, task)
  return task
}

// 解析 PNG/JPEG 尺寸
function imageSize(b64) {
  try {
    const bin = atob(b64)
    const u8 = (i) => bin.charCodeAt(i)
    if (bin.charCodeAt(0) === 0x89 && bin.charCodeAt(1) === 0x50) {
      return {
        w: (u8(16) << 24) | (u8(17) << 16) | (u8(18) << 8) | u8(19),
        h: (u8(20) << 24) | (u8(21) << 16) | (u8(22) << 8) | u8(23),
        ext: 'png',
      }
    }
    if (bin.charCodeAt(0) === 0xff && bin.charCodeAt(1) === 0xd8) {
      let i = 2
      while (i < bin.length - 9) {
        if (u8(i) !== 0xff) {
          i++
          continue
        }
        const marker = u8(i + 1)
        const len = (u8(i + 2) << 8) | u8(i + 3)
        if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
          return { h: (u8(i + 5) << 8) | u8(i + 6), w: (u8(i + 7) << 8) | u8(i + 8), ext: 'jpeg' }
        }
        i += 2 + len
      }
    }
  } catch (e) {
    /* 忽略 */
  }
  return { w: 300, h: 300, ext: 'png' }
}

function itemLineCents(item) {
  return inputToCents(item.unitPrice) * (parseInt(item.qty, 10) || 0)
}

// 导出 Word 时整数金额不带 .00，非整数仍保留两位小数
function docCents(cents) {
  const n = Number(cents) || 0
  return n % 100 === 0 ? formatMoney0(n / 100) : formatCents(n)
}

function payTextOf(totalCents, payMode) {
  if (payMode === 'p30') {
    const prepay = Math.round(totalCents * 0.3)
    const rest = totalCents - prepay
    return `本产品订单总金额为${docCents(totalCents)}元，甲方签订合同后10个工作日内向乙方支付30%预付款，即${docCents(prepay)}元。乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，甲方收到通知后支付剩余尾款${docCents(rest)}元。乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的13%增值税专用发票。`
  }
  if (payMode === 'p50') {
    const prepay = Math.round(totalCents * 0.5)
    const rest = totalCents - prepay
    return `本产品订单总金额为${docCents(totalCents)}元，甲方签订合同后10个工作日内向乙方支付50%预付款，即${docCents(prepay)}元。乙方在收到预付款后20个自然日内完成生产，乙方生产完成后通知甲方，甲方收到通知后支付剩余尾款${docCents(rest)}元。乙方应在甲方收货检验合格10个工作日内向甲方开具等额合法有效的13%增值税专用发票。`
  }
  return `本产品订单总金额为${docCents(totalCents)}元，签订本产品订购清单，并经甲乙双方确认当次甲方应付金额后，甲方应及时向乙方付款。乙方应在甲方支付全部款项后7个工作日内向甲方开具等额合法有效的13%增值税专用发票。`
}

function mainContractDateText(iso) {
  const md = String(iso || '').slice(0, 10)
  if (!md) return '【      】年【     】月【     】日'
  const p = md.split('-').map(Number)
  return `【${p[0]}】年【${p[1]}】月【${p[2]}】日`
}

export async function buildOrderDocx({
  supplier,
  items,
  payMode,
  totalCents,
  partyA,
  mainContractDate,
}) {
  const supplierName = (supplier && supplier.name) || '＿＿＿＿＿＿＿＿＿＿'
  const partyAName = (partyA && partyA.name) || '＿＿＿＿＿＿＿＿＿＿'
  const b64List = await Promise.all(items.map((it) => (it.image ? loadImageB64(it.image) : null)))
  const doc = new DocxBuilder()

  doc.paras.push({ t: '产品订购清单', align: 'center', bold: true, size: 32, spaceAfter: 240 })

  const info = [
    `购货单位（甲方）：${partyAName}`,
    `供货单位（乙方）：${supplierName}`,
    '交货地址：广州市花都区花都沿江大道24号永日电梯（昊运仓储公司）张生 17675625750',
  ]
  info.forEach((s) => doc.paras.push({ t: s, size: 21, line: 340 }))
  doc.paras.push({
    t: '（送货记得打托，送货单：包含箱数，箱规，尾货散货做好标记）',
    size: 18,
    color: '666666',
    line: 340,
    spaceAfter: 160,
  })
  doc.paras.push({
    t: `甲乙双方已于${mainContractDateText(mainContractDate)}签订了《购销框架合同》（以下简称“主合同”），现双方协商一致特签订本《产品订购清单》，乙方按以下表格内容及要求及时提供产品：`,
    size: 21,
    line: 340,
    spaceAfter: 160,
  })

  const widths = [1700, 1300, 1500, 900, 1000, 1300, 1340]
  const heads = ['商品名称', '商品图片', '规格', '数量（个）', '单个价格', '总金额', '备注']
  doc.table = { widths, rows: [] }
  doc.table.rows.push(heads.map((h) => ({ text: h, align: 'center', bold: true, shade: GREEN })))

  items.forEach((it, index) => {
    const b64 = b64List[index]
    let imgCell
    if (b64) {
      const size = imageSize(b64)
      let wT = Math.min(1100, size.w * 15)
      let hT = Math.round((wT * size.h) / size.w)
      if (hT > 1100) {
        hT = 1100
        wT = Math.round((hT * size.w) / size.h)
      }
      imgCell = { image: b64, ext: size.ext, wtwips: wT, htwips: hT }
    } else {
      imgCell = { text: '', align: 'center' }
    }
    doc.table.rows.push([
      { text: it.name, shade: GREEN },
      imgCell,
      { text: it.spec || '', shade: GREEN },
      { text: it.qty || '', align: 'right', shade: GREEN },
      { text: `${docCents(inputToCents(it.unitPrice))} 元`, align: 'right', shade: GREEN },
      { text: `${docCents(itemLineCents(it))} 元`, align: 'right', shade: GREEN },
      { text: (it.remark || '').trim(), shade: GREEN },
    ])
  })

  doc.table.rows.push([
    { text: '合计（含税）', align: 'center', bold: true, gridSpan: 4, shade: GREEN },
    {
      text: `¥${docCents(totalCents)} 元，除前述费用外，甲方无需支付其他费用，乙方应按甲方的要求提供货物。`,
      bold: true,
      gridSpan: 3,
      shade: GREEN,
    },
  ])

  const now = new Date()
  const dayText = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
  const after = [
    { t: '1. 结算方式：' },
    { t: payTextOf(totalCents, payMode) },
    { t: '2. 交货时间：乙方应在【2026】年【　】月【　】日前向甲方提供上述产品。' },
    {
      t: '3. 本《产品订购清单》作为双方已签订的主合同的一部分，与主合同约定不一致的，以本清单约定为准；本清单内未约定的事宜以双方签订的主合同为准。',
    },
    { t: '4. 本《产品订购清单》自双方盖章之日起生效，一式贰份，双方各执壹份，具有同等法律效力。' },
    { t: '（此行以下无正文）', size: 18, color: '666666', spaceAfter: 280 },
    {
      t: `甲方：${partyAName}　　　　乙方：${supplierName}`,
      spaceBefore: 200,
      spaceAfter: 240,
    },
    { t: '（盖章）　　　　　　　　　　　　　　　　（盖章）', spaceAfter: 240 },
    { t: `签署日期：${dayText}　　　　　　　　　　签署日期：${dayText}` },
  ]
  after.forEach((p) => doc.paras2.push(Object.assign({ size: 21, line: 360 }, p)))

  const mainDate = String(mainContractDate || '').slice(0, 10)
  const tag = mainDate ? `_主合同${dateDigits(mainDate)}` : ''
  return {
    blob: doc.build(),
    filename: `产品订购清单_${supplierName}_${dateDigits(dayText)}${tag}.docx`,
  }
}

export function buildMainContractDocx(supplier, threshold = 70000, partyA) {
  const supplierName = (supplier && supplier.name) || '＿＿＿＿＿＿＿＿＿＿'
  const partyAName = (partyA && partyA.name) || '＿＿＿＿＿＿＿＿＿＿'
  const supplierTel = (supplier && supplier.phone) || '＿＿＿＿＿＿＿＿'
  const now = new Date()
  const dayText = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
  const endDate = new Date(now.getFullYear() + 1, now.getMonth(), now.getDate())
  endDate.setDate(endDate.getDate() - 1)

  const doc = new DocxBuilder()
  const P = (t, o) => doc.paras.push(Object.assign({ t, size: 21, line: 340 }, o || {}))

  P('购销框架合同', { align: 'center', bold: true, size: 32, spaceAfter: 240, line: 300 })
  P('甲方（购货方）：' + partyAName)
  P('乙方（供货方）：' + supplierName)
  P(
    '根据《中华人民共和国民法典》及其有关法律法规，为明确甲乙双方的权利义务，甲、乙双方经友好协商，就乙方在合作期内为甲方供应产品，达成如下框架合同：',
    { spaceAfter: 200 },
  )

  P('一、产品的供应', { bold: true })
  P(
    '1、乙方向甲方供应产品的品种、数量、交货日期、交货地点及价格以附件的《产品订购清单》为准。甲方如有新的需求，可在本合同有效期限内与乙方继续签订《产品订购清单》。',
  )
  P('2、乙方接到甲方的购买需求时，应另行准备一定的数量作为备用量，以便及时退换。', { spaceAfter: 160 })

  P('二、产品的质量与保证', { bold: true })
  P(
    '1、乙方向甲方供应的产品的质量应当符合该产品的国家标准和行业标准，没有国家标准和行业标准的按照通常标准或符合合同目的的特定标准。',
  )
  P(
    '2、在乙方每次向甲方供应产品时，双方可在《产品订购清单》上对该产品的具体质量标准进行约定。乙方在向甲方交付产品的同时应当提交所供应产品合格证或质量保证书。',
  )
  P(
    '3、乙方应对其供应的产品质量负责，承担因其产品存在质量问题所引起的全部责任，并赔偿因此给甲方造成的全部损失。乙方保证产品质量保证期为【1】年，自甲方收到货物时起算。',
    { spaceAfter: 160 },
  )

  P('三、供应产品的具体内容', { bold: true })
  P(
    '供货方式采用乙方一次性发货，除非甲方要求乙方分开发货，发货的运费全部均由乙方承担，若甲方有特殊要求的，则由甲乙双方协商解决。',
    { spaceAfter: 160 },
  )

  P('四、验收及标准', { bold: true })
  P(
    '1、对于乙方供应的产品，甲方在验收时采用本合同第二条的约定及国家相关法律法规规定作为验收标准及退换货依据。',
  )
  P(
    '2、甲方在验收时，如发现产品不符合验收标准的，有权拒收不合格产品或要求乙方退换，乙方需在甲方要求后【3】日内如数补足或重新交付产品并经验收合格。',
    { spaceAfter: 160 },
  )

  P('五、供应产品的退换货', { bold: true })
  P('1、乙方在任何时候须保证无条件退换不符合本合同约定及/或甲方要求的产品或者存在质量问题的产品。')
  P('2、因乙方产品质量问题或非甲方原因导致的退换货，产生的全部运费及其他相关费用均由乙方负责。', {
    spaceAfter: 160,
  })

  P('六、结算方式', { bold: true })
  P(
    `1、甲方以银行转账的方式向乙方支付相应款项，具体的结算方式以双方另行签订的《产品订购清单》约定为准。订单总金额低于人民币${formatMoney0(threshold)}元的适用全额付款；达到${formatMoney0(threshold)}元及以上的，可选择30%或50%预付款方式。`,
  )
  P(
    '2、乙方保证向甲方提供的发票为合法有效的。乙方应在收到货款后【15】个工作日内向甲方开具等额合法有效的税率为【13%】的增值税专用发票。',
  )
  P('3、乙方收款账户信息：')
  P('开户名称：' + supplierName)
  P('账　　号：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿')
  P('开户行：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿', { spaceAfter: 160 })

  P('七、双方权利义务', { bold: true })
  P(
    '1、乙方应当保证其为所供应产品的品牌方，有权授权甲方在线上或线下售卖或赠送本协议项下的产品，保证其所供应的产品及推广素材符合国家相关法律法规的要求，不存在任何知识产权的瑕疵。',
  )
  P('2、双方在合作过程中获知的对方的商业秘密、订购信息等保密信息，在任何时候均不得向第三方披露或公开。', {
    spaceAfter: 160,
  })

  P('八、违约责任', { bold: true })
  P('1、任何一方没有充分、及时履行义务的，应当承担违约责任，赔偿给对方造成的全部损失。')
  P('2、乙方逾期发货的，每逾期一天按逾期发货产品总价的1%计算违约金。乙方逾期超过7天的，甲方有权取消本订单。')
  P(
    '3、乙方不得向甲方员工、顾问等相关团队人员提供任何形式的不正当利益（款项或实物金额超过200元），否则甲方有权单方解除本协议且不承担任何违约责任。',
    { spaceAfter: 160 },
  )

  P('九、争议及诉讼管辖', { bold: true })
  P('甲乙双方因履行本合同发生争议的，应友好协商解决；协商不成的，双方同意由甲方所在地人民法院管辖。', {
    spaceAfter: 160,
  })

  P('十、其他', { bold: true })
  P(
    `1、本合同期限为【壹】年，自【${now.getFullYear()}】年【${now.getMonth() + 1}】月【${now.getDate()}】日起至【${endDate.getFullYear()}】年【${endDate.getMonth() + 1}】月【${endDate.getDate()}】日止。`,
  )
  P('2、本合同自双方盖章之日起生效，一式贰份，甲乙双方各执壹份，具有同等法律效力。')
  P('3、本合同附件《产品订购清单》作为本合同的一部分，与本合同具有同等法律效力。', { spaceAfter: 320 })

  P(`甲方（盖章）：${partyAName}　　　　乙方（盖章）：${supplierName}`)
  P('法定代表人（签字/盖章）：　　　　　　　　　　　法定代表人（签字/盖章）：')
  P(`乙方联系电话：${supplierTel}`)
  P(`签署日期：${dayText}　　　　　　　　　　签署日期：${dayText}`, { spaceBefore: 160 })

  return {
    blob: doc.build(),
    filename: `购销框架合同_${supplierName}_${dateDigits(dayText)}.docx`,
  }
}

export function downloadDocx(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 3000)
}

export function payModeLabel(mode) {
  return { full: '全额付款', p30: '30% 预付 + 70% 尾款', p50: '50% 预付 + 50% 尾款' }[mode] || ''
}

export function payTextPreview(totalCents, mode) {
  if (!totalCents) return ''
  if (mode === 'p30') {
    const prepay = Math.round(totalCents * 0.3)
    return `预付款 ¥${formatMoney(prepay / 100)}（30%），尾款 ¥${formatMoney((totalCents - prepay) / 100)}（70%）`
  }
  if (mode === 'p50') {
    const prepay = Math.round(totalCents * 0.5)
    return `预付款 ¥${formatMoney(prepay / 100)}（50%），尾款 ¥${formatMoney((totalCents - prepay) / 100)}（50%）`
  }
  return `全额付款 ¥${formatCents(totalCents)}`
}
