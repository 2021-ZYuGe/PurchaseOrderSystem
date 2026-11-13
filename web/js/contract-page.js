// 合同页逻辑：主合同新签 / 续签、信息收集表、存入档案
// 从 contract.html 内联脚本抽出（P3），保持原有全局函数名以兼容内联 onclick

let MODE = '', TYPE = 'batch', ARCH = [];   // 第 1 步未选之前为空，避免「选供应商」还没出现就冒出一个 3
let PAY_MODE = 'full', PAY_THRESHOLD = 70000;

function $(id){ return document.getElementById(id); }
function get(id){ return ($(id) || {}).value || ''; }
function money0(n){ return Number(n).toLocaleString('zh-CN', {maximumFractionDigits:0}); }

// 甲方公司 -> 统一社会信用代码（一一对应）
const PARTY_A_CODES = {
  '广州兴趣岛信息科技有限公司': '91440104MA59C33C5N',
  '广州普惠优品电子商贸有限公司': '91440106MA7LKA4517'
};
function syncPartyACode(){
  const code = PARTY_A_CODES[get('a_name')] || '';
  if ($('a_credit_code')) $('a_credit_code').value = code;
}

// ---- 模式 / 类型切换 ----
// 步骤号跟着当前显示的卡片走：首次签约没有「选供应商」这一步，后面的编号要整体前移，
// 不能出现 1 → 3 的跳号；没选第 1 步时，合同类型排第 2。
function renumberSteps(){
  let n = 0;
  document.querySelectorAll('.card').forEach(card => {
    const badge = card.querySelector('h2 .step');
    if (!badge || !card.offsetParent) return;   // 没有序号 / 当前隐藏的卡片不占号
    badge.textContent = String(++n);
  });
}

document.getElementById('modeBox').onclick = function(e){
  const el = e.target.closest('.mode-opt'); if(!el) return;
  MODE = el.dataset.mode;
  [...this.children].forEach(c => c.classList.toggle('active', c === el));
  $('cardPick').style.display = MODE === 'renew' ? '' : 'none';
  if (MODE === 'new') { $('pickedBox').classList.remove('show'); clearB(); }
  renumberSteps();
};
// 每种合同类型对应模板里黄色高亮、必须由用户填写的字段
const REQUIRED = {
  batch: [
    ['b_name','公司全称'], ['b_credit_code','统一社会信用代码'],
    ['b_contact','联系人'], ['b_tel','联系电话'], ['b_email','联系邮箱'], ['b_addr','联系地址'],
    ['b_bank_name','开户名称'], ['b_bank_account','对公账号'], ['b_bank_open','开户行'],
    ['s_date','签约日期'], ['s_years','合同期限（年）'], ['t_order_amount','本次订单总金额']
  ],
  simple: [
    ['b_name','公司全称'], ['b_contact','联系人'], ['b_tel','联系电话'], ['b_email','联系邮箱'],
    ['b_addr','联系地址'], ['b_bank_name','开户名称'], ['b_bank_account','开户账号'], ['b_bank_open','开户行'],
    ['s_date','签约日期'], ['t_order_amount','本次订单总金额']
  ],
  dropship: [
    ['b_name','公司全称'], ['b_addr','联系地址'], ['b_bank_account','对公账号'],
    ['b_bank_open','开户行'], ['s_date','签约日期']
  ]
};
const REQ_HINT = {
  batch: '批采必填（对应模板黄色高亮）：公司全称、信用代码、联系人、电话、邮箱、地址、开户名称、对公账号、开户行、订单总金额、合同期限。',
  simple: '简易版必填（对应模板黄色高亮）：公司全称、联系人、电话、邮箱、地址、开户名称、开户账号、开户行、订单总金额。',
  dropship: '一件代发必填：公司全称、联系地址、对公账号、开户行、签约日期。'
};

function updateReqMarks(){
  document.querySelectorAll('.dyn-req').forEach(el => {
    const types = (el.dataset.req || '').split(/\s+/);
    el.style.display = types.includes(TYPE) ? '' : 'none';
  });
}

function updateTypeUI(){
  const dropship = TYPE === 'dropship';
  $('fRecon').style.display = dropship ? '' : 'none';
  $('fInvPct').style.display = dropship ? '' : 'none';
  $('fYears').style.display = TYPE === 'simple' ? 'none' : '';   // 简易版没有合同期限
  $('fAmount').style.display = dropship ? 'none' : '';
  // 批采 / 简易版：付款条款按所选模式固定生成；代发仍用原来的账期字段
  $('payModeBox').style.display = dropship ? 'none' : '';
  $('fInvoiceDays').style.display = dropship ? '' : 'none';
  $('fPayDays').style.display = dropship ? '' : 'none';
  if (dropship) PAY_MODE = 'full';
  $('reqHint').textContent = REQ_HINT[TYPE] || '';
  updateReqMarks();
  updatePayModeUI();
}

function updatePayModeUI(){
  const total = parseFloat(get('t_order_amount').replace(/,/g, '')) || 0;
  const below = !total || total < PAY_THRESHOLD;
  const opts = $('payModes').querySelectorAll('.pay-mode');
  opts.forEach(o => {
    const isFull = o.dataset.pay === 'full';
    const restricted = below && !isFull;
    o.classList.toggle('disabled', restricted);
    if (restricted && PAY_MODE === o.dataset.pay) PAY_MODE = 'full';
  });
  if (below) PAY_MODE = 'full';
  opts.forEach(o => o.classList.toggle('active', o.dataset.pay === PAY_MODE));
  const note = $('payModeNote');
  if (!total) note.textContent = '先填写本次订单总金额，再选择付款方式。';
  else if (below) note.textContent = `订单总金额 ${money0(total)} 元 ＜ ${money0(PAY_THRESHOLD)} 元，只能全款。`;
  else note.textContent = `订单总金额 ${money0(total)} 元 ≥ ${money0(PAY_THRESHOLD)} 元，可选择预付款方式。`;
}

function initPayMode(){
  const v = parseFloat(localStorage.getItem('payThreshold'));
  PAY_THRESHOLD = Number.isFinite(v) && v >= 0 ? v : 70000;
  $('t_pay_threshold').value = String(PAY_THRESHOLD);
  $('t_pay_threshold').addEventListener('input', () => {
    const n = parseFloat($('t_pay_threshold').value);
    PAY_THRESHOLD = Number.isFinite(n) && n >= 0 ? n : 0;
    localStorage.setItem('payThreshold', String(PAY_THRESHOLD));
    updatePayModeUI();
  });
  $('t_order_amount').addEventListener('input', updatePayModeUI);
  $('payModes').addEventListener('click', e => {
    const opt = e.target.closest('.pay-mode');
    if (!opt || opt.classList.contains('disabled')) return;
    PAY_MODE = opt.dataset.pay;
    updatePayModeUI();
  });
}

document.getElementById('typeBox').onclick = function(e){
  const el = e.target.closest('.mode-opt'); if(!el) return;
  TYPE = el.dataset.type;
  [...this.children].forEach(c => c.classList.toggle('active', c === el));
  updateTypeUI();
};

// ---- 档案 ----
fetch('/api/archive', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})
  .then(r => r.json()).then(j => {
    if (!j.ok) return;
    ARCH = (j.data && j.data.suppliers) || [];
    $('archCount').textContent = ARCH.length;
    const dl = $('supList');
    ARCH.forEach(s => { const o = document.createElement('option'); o.value = s.name; dl.appendChild(o); });
    const pa = (j.data && j.data.party_a) || {};
    // v2：旧的 partyA 里可能存着过期信息，首次打开先显示页面预填的默认甲方信息
    const saved = JSON.parse(localStorage.getItem('partyA_v2') || '{}');
    // 只覆盖有值的字段：空值保留页面预填的默认甲方信息
    ['name','credit_code','contact','tel','email','addr'].forEach(k => {
      const el = $('a_' + k);
      if (!el) return;
      const v = String(saved[k] || pa[k] || '').trim();
      if (v) el.value = v;
    });
    if (!get('a_name')) $('a_name').value = '广州兴趣岛信息科技有限公司';
    syncPartyACode();
  }).catch(()=>{});

$('supInput').addEventListener('change', pickSup);
$('supInput').addEventListener('input', function(){
  const v = this.value.trim();
  if (!v) return;
  const hit = ARCH.find(s => s.name === v);
  if (hit) pickSup();
});
function pickSup(){
  const v = $('supInput').value.trim();
  const hit = ARCH.find(s => s.name === v) || ARCH.find(s => s.name.includes(v) && v.length > 3);
  if (!hit) return;
  fillB(hit);
  const amtTxt = hit.last_order_amount
    ? '；最近合同金额 ¥' + Number(hit.last_order_amount).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2})
      + (hit.last_order_date ? '（' + hit.last_order_date + '）' : '')
    : '';
  $('pickedBox').innerHTML = '已带入 <b>' + hit.name + '</b> 的历史信息'
    + (hit.last_sign ? '（上次签约：' + hit.last_sign + '）' : '')
    + amtTxt
    + '。<br>请重点核对：账号、开户行、税率、金额、这次的签约日期。'
    + expiryTip(hit.name);
  $('pickedBox').classList.add('show');
}

// 当前合同还剩多久到期：续签时用于确认是不是该续了
let EXPIRY_MAP = {};
fetch('/api/contract_expiry', {cache:'no-store'})
  .then(r => r.json())
  .then(j => {
    if (!j || !j.ok || !j.data) return;
    (j.data.items || []).forEach(it => { EXPIRY_MAP[it.供应商] = it; });
  }).catch(() => {});

function expiryTip(name){
  const ex = EXPIRY_MAP[name];
  if (!ex || !ex.到期日) return '';
  const dl = ex.剩余天数;
  const txt = dl < 0 ? '已过期 ' + (-dl) + ' 天' : '剩 ' + dl + ' 天';
  const color = dl < 0 ? '#c62828' : (dl <= 30 ? '#b26a00' : '#1b5e20');
  return '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed rgba(0,0,0,.12);'
    + 'color:' + color + ';font-weight:600">当前合同：' + (ex.起始日 ? ex.起始日 + ' 至 ' : '至 ')
    + ex.到期日 + '（' + txt + '）'
    + (dl <= 30 ? '，建议按续签办理' : '') + '</div>';
}
function fillB(s){
  ['name','credit_code','contact','tel','email','wechat','addr','bank_name','bank_account','bank_open']
    .forEach(k => { const el = $('b_' + k); if (el) el.value = s[k] || ''; });
  // 开户名称默认等于公司全称，避免档案里没存这一项时留空
  if (!$('b_bank_name').value.trim()) $('b_bank_name').value = s.name || '';
  // 续签：带入该供应商最近一份合同的订单总金额，用户仍可改
  $('t_order_amount').value = s.last_order_amount ? String(s.last_order_amount) : '';
  updatePayModeUI();
}
$('b_name').addEventListener('change', function(){
  const bn = $('b_bank_name');
  if (bn && !bn.value.trim()) bn.value = this.value.trim();
});
function clearB(){
  ['name','credit_code','contact','tel','email','wechat','addr','bank_name','bank_account','bank_open']
    .forEach(k => { const el = $('b_' + k); if (el) el.value = ''; });
  $('t_order_amount').value = '';
  updatePayModeUI();
}

// ---- 甲方记忆 ----
['name','credit_code','contact','tel','email','addr'].forEach(k => {
  const el = $('a_' + k);
  if (el) el.addEventListener('change', () => {
    const o = {}; ['name','credit_code','contact','tel','email','addr'].forEach(x => o[x] = get('a_' + x));
    localStorage.setItem('partyA_v2', JSON.stringify(o));
  });
});

// ---- 收集数据 ----
function collect(){
  return {
    contract_type: TYPE,
    remember: MODE === 'new',
    party_a: { name:get('a_name'), credit_code:get('a_credit_code'), contact:get('a_contact'),
               tel:get('a_tel'), email:get('a_email'), addr:get('a_addr') },
    party_b: { name:get('b_name'), credit_code:get('b_credit_code'),
               contact:get('b_contact'), tel:get('b_tel'), email:get('b_email'), wechat:get('b_wechat'),
               addr:get('b_addr'), bank_name:get('b_bank_name'),
               bank_account:get('b_bank_account'), bank_open:get('b_bank_open') },
    sign: { date:get('s_date'), years:get('s_years'), place:get('s_place') },
    terms: { tax_rate:get('t_tax_rate'), invoice_type:get('t_invoice_type'),
             invoice_days:get('t_invoice_days'), pay_days:get('t_pay_days'),
             delivery_days:get('t_delivery_days'), reconcile_days:get('t_reconcile_days'),
             invalid_order_pct:get('t_invalid_order_pct'),
             delivery_addr:get('t_delivery_addr'),
             order_amount:get('t_order_amount').replace(/,/g,'').trim(),
             pay_mode: PAY_MODE }
  };
}
function show(cls, text){ const m = $('msg'); m.className = 'msg show ' + cls; m.innerHTML = text; }

function post(url, payload){
  return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify(payload)})
    .then(r => r.text())
    .then(text => {
      try { return JSON.parse(text); }
      catch (e) {
        // 静态预览服务（python -m http.server）不支持 POST，会返回一段 HTML，
        // 直接 r.json() 只会报“Unexpected token '<'”，这里换成能看懂的提示。
        return {ok:false, error:'当前页面是“网页预览”模式，只能浏览网页，不能生成合同。'
          + '请关闭本页，双击文件夹里的「启动网页版.bat」重新启动系统后再试。'};
      }
    });
}

function validateForGenerate(){
  // 开户名称默认跟公司全称，避免用户重复输入
  if (!$('b_bank_name').value.trim() && $('b_name').value.trim()) {
    $('b_bank_name').value = $('b_name').value.trim();
  }
  const missing = [];
  let first = null;
  (REQUIRED[TYPE] || []).forEach(([id, label]) => {
    const el = $(id);
    if (el && !String(el.value || '').trim()) {
      missing.push(label);
      if (!first) first = el;
    }
  });
  if (missing.length) {
    show('err', '以下必填项还没填（对应模板里的黄色高亮）：<b>' + missing.join('、') + '</b>');
    if (first) {
      first.focus();
      try { first.scrollIntoView({block:'center', behavior:'smooth'}); } catch (e) {}
    }
    return false;
  }
  if (TYPE !== 'dropship') {
    const raw = get('t_order_amount').replace(/,/g, '').trim();
    if (!/^\d+(\.\d{1,2})?$/.test(raw) || parseFloat(raw) <= 0) {
      show('err', '本次订单总金额请填数字，例如 12500 或 12500.50。');
      $('t_order_amount').focus();
      return false;
    }
  }
  if (TYPE === 'batch' && !/^[1-9]\d*$/.test(get('s_years').trim())) {
    show('err', '合同期限请填正整数年数，例如 1。');
    $('s_years').focus();
    return false;
  }
  const numFields = [['t_delivery_days', '交货周期']];
  if (TYPE === 'dropship') numFields.push(['t_invoice_days', '开票期限'], ['t_pay_days', '付款期限']);
  for (const [id, label] of numFields) {
    if (!/^\d+$/.test(get(id).trim())) {
      show('err', label + '请填数字。');
      $(id).focus();
      return false;
    }
  }
  return true;
}

function generate(){
  if (!MODE) {
    show('err', '先在第 1 步选一下：这次是「续签 / 到期重签」还是「首次签约」。选完步骤号会自动排好，新供应商的信息也才会存进档案。');
    try { $('modeBox').scrollIntoView({block:'center', behavior:'smooth'}); } catch (e) {}
    return;
  }
  if (!validateForGenerate()) return;
  $('btnGen').disabled = true; $('btnGen').textContent = '生成中…';
  post('/api/make_contract', collect()).then(r => {
    $('btnGen').disabled = false; $('btnGen').textContent = '生成合同 Word';
    if (!r.ok) { show('err','生成失败：' + (r.error || '未知错误')); return; }
    let tip = '已生成 <b>' + r.name + '</b>，正在下载…<br>打开看一下，重点核对：公司名 / 账号 / 开户行 / 税率 / 金额 / 日期。';
    if (r.todo && r.todo.length) {
      tip += '<br><b style="color:#b7791f">还有 ' + r.todo.length +
             ' 处要你手工确认</b>（模板里没有默认值的条款）：<ul style="margin:6px 0 0 18px">';
      r.todo.forEach(t => { tip += '<li>' + String(t).replace(/</g,'&lt;').slice(0,80) + '</li>'; });
      tip += '</ul>';
    }
    tip += (MODE === 'new' ? '<br>这家供应商的信息已自动存入档案，下次续签直接搜名字就能带出来。' : '');
    show('ok', tip);
    setTimeout(() => { location.href = r.url; }, 600);
  }).catch(e => {
    $('btnGen').disabled = false; $('btnGen').textContent = '生成合同 Word';
    show('err','连接服务失败：' + e + '<br>请关闭本页，双击文件夹里的「启动网页版.bat」重新启动系统。');
  });
}

function exportInfo(){
  const p = collect();
  if (!p.party_b.name) { show('err','先填一下乙方公司名，收集表上会带上名字。'); return; }
  post('/api/make_info_sheet', p).then(r => {
    if (!r.ok) { show('err','失败：' + (r.error || '')); return; }
    show('ok','<b>' + r.name + '</b> 已生成，正在下载。<br>直接微信发给对方，让他照着填回来。');
    setTimeout(() => { location.href = r.url; }, 600);
  });
}

function saveOnly(){
  const b = collect().party_b;
  if (!b.name) { show('err','公司名不能为空。'); return; }
  post('/api/save_supplier', b).then(r => {
    show(r.ok ? 'ok' : 'err', r.ok ? '已存入档案。下次在「续签」里搜名字就能自动带出来。' : '保存失败');
    if (r.ok) fetch('/api/archive',{method:'POST',body:'{}'}).then(x=>x.json()).then(j=>{
      ARCH = (j.data && j.data.suppliers) || [];
      $('archCount').textContent = ARCH.length;
    });
  });
}

// 默认今天
$('s_date').value = new Date().toISOString().slice(0,10);
syncPartyACode();
initPayMode();
updateTypeUI();
renumberSteps();
