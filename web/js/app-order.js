// order
// 产品搜索、下单清单、金额计算、付款方式。

const prodInput = document.getElementById("prodInput");
const prodResults = document.getElementById("prodResults");
let prodSeq = 0;
let prodTimer = null;

prodInput.addEventListener("input", () => {
  const raw = prodInput.value.trim();
  const q = norm(raw);
  clearTimeout(prodTimer);
  if (!q) { prodResults.classList.remove("show"); return; }
  // 轻微防抖：避免每敲一个字都打一次接口
  prodTimer = setTimeout(() => runProductSearch(raw, q), 120);
});

function showProdMessage(text) {
  prodResults.innerHTML = '<div class="sr-item"><div class="d">' + text + '</div></div>';
  prodResults.classList.add("show");
}

async function runProductSearch(raw, q) {
  const seq = ++prodSeq;
  const supplier = state.supplier ? state.supplier.id : "";
  let items;
  try {
    const data = await fetchJSON(
      "/api/products?q=" + encodeURIComponent(raw) +
      "&limit=20&supplier=" + encodeURIComponent(supplier));
    items = data.items || [];
  } catch (e) {
    if (seq === prodSeq) showProdMessage("搜索失败：" + e.message);
    return;
  }
  // 输入已经变了就丢弃这次结果，避免慢响应盖住新结果
  if (seq !== prodSeq || prodInput.value.trim() !== raw) return;
  const supKeys = new Set(state.supplier ? state.supplier["产品keys"] : []);
  renderResults(prodResults, items, p => {
    const alias = (p.别名 || []).filter(a => norm(a).includes(q));
    const imgKey = p.图片 ? `${p.id}|${p.图片}` : p.id;
    return {
      t: `${p.图片 ? `<img class="thumb" src="图片/${p.图片}" onerror="this.style.display='none'">` : ""}${hl(p.产品名称, q)}`
        + (p.备选图片 && p.备选图片.length ? `<span class="tag">${p.备选图片.length + 1}图</span>` : ""),
      d: (alias.length ? `别名 ${alias.map(a=>hl(a,q)).join("、")} · ` : "")
        + `${p.规格 ? "规格 " + hl(p.规格, q) + " · " : ""}历史价 ${p.历史单价.length ? "¥"+p.历史单价.join("/¥") : "—"} · 下单${p.下单次数}次`
        + (supKeys.has(p.id) ? " · ★该供应商产品" : ""),
      _key: imgKey,
    };
  }, item => {
    addProduct(item, item._key);
    prodInput.value = "";
    prodResults.classList.remove("show");
  });
}

function addProduct(p, key) {
  const k = key || p.id;
  if (state.items.find(i => i.key === k)) return;
  const lastPrice = p.历史单价.length ? p.历史单价[0] : "";
  const imgs = [p.图片, ...(p.备选图片 || [])].filter(Boolean);
  state.items.push({
    key: k, 产品名称: p.产品名称, 规格: p.规格, 图片: imgs[0] || "", 图片集: imgs,
    单价: lastPrice, 数量: "", 备注: DEFAULT_REMARK, 历史单价: p.历史单价,
  });
  renderItems();
}

// 切换该产品使用的图片
function cycleImg(key) {
  const it = state.items.find(i => i.key === key);
  if (!it || !it.图片集 || it.图片集.length < 2) return;
  const i = it.图片集.indexOf(it.图片);
  it.图片 = it.图片集[(i + 1) % it.图片集.length];
  renderItems();
}

function removeItem(key) {
  state.items = state.items.filter(i => i.key !== key);
  renderItems();
}

function renderItems() {
  const tb = document.getElementById("prodTbody");
  tb.innerHTML = "";
  document.getElementById("prodCount").textContent = `已选 ${state.items.length} 个产品`;
  state.items.forEach(item => {
    const tr = document.createElement("tr");
    const multi = item.图片集 && item.图片集.length > 1;
    tr.innerHTML = `
      <td style="position:relative">${item.图片 ? `<img src="图片/${item.图片}" onclick="showImg(this.src)" onerror="imgErr(this)">`
        : `<img class="noimg" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E" alt="无图" style="display:flex;align-items:center;justify-content:center" onclick="imgErr(this)">`}
        ${multi ? `<div class="img-switch" title="切换图片 (${item.图片集.length}张)" onclick="cycleImg('${item.key}')">⇄</div>` : ""}</td>
      <td><b>${item.产品名称}</b>${item.历史单价.length ? `<div class="hint">历史价: ${item.历史单价.slice(0,3).map(v=>"¥"+v).join(" / ")}</div>` : ""}${multi ? `<div class="hint">共 ${item.图片集.length} 张备选图，点图右上角 ⇄ 切换</div>` : ""}</td>
      <td>${item.规格 ? `<span style="font-size:12px;color:#5f6b7a">${item.规格}</span>` : '<span class="hint">—</span>'}</td>
      <td><input type="number" class="price-input" step="0.01" min="0" value="${item.单价}" placeholder="0.00"
        oninput="setItem('${item.key}','单价',this.value)"></td>
      <td><input type="number" step="1" min="0" value="${item.数量}" placeholder="0"
        oninput="setItem('${item.key}','数量',this.value)"></td>
      <td class="amt" id="amt_${item.key}">—</td>
      <td><input type="text" class="remark-input" value="${(item.备注||"").replace(/"/g,"&quot;")}" placeholder="${DEFAULT_REMARK}"
        oninput="setItem('${item.key}','备注',this.value)"></td>
      <td><button class="btn-del" onclick="removeItem('${item.key}')">✕</button></td>
    `;
    tb.appendChild(tr);
  });
  document.getElementById("cardPay").style.display = state.items.length ? "" : "none";
  document.getElementById("cardTotal").style.display = state.items.length ? "" : "none";
  calc();
}

function imgErr(el) {
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.fontSize = "10px";
  el.style.color = "#c0c8d2";
  el.style.background = "#f5f7fa";
  el.alt = "无图";
  el.removeAttribute("src");
}

function setItem(key, field, val) {
  const it = state.items.find(i => i.key === key);
  if (!it) return;
  it[field] = val;
  calc();
}

function itemAmount(it) {
  const p = parseFloat(it.单价) || 0;
  const q = parseFloat(it.数量) || 0;
  return p * q;
}

function grandTotal() {
  return state.items.reduce((s, it) => s + itemAmount(it), 0);
}

function calc() {
  let total = 0;
  state.items.forEach(it => {
    const a = itemAmount(it);
    const el = document.getElementById("amt_" + it.key);
    if (el) el.textContent = a ? fmt(a) : "—";
    total += a;
  });
  document.getElementById("grandTotal").textContent = fmt(total);
  updatePayOptions(total);
}

// ============ 付款方式 ============
// 预付款起订金额：可在页面上自行改，记在本机浏览器里
const DEFAULT_THRESHOLD = 70000;
const THRESHOLD_KEY = "payThreshold";
let PAY_THRESHOLD = (() => {
  const v = parseFloat(localStorage.getItem(THRESHOLD_KEY));
  return Number.isFinite(v) && v >= 0 ? v : DEFAULT_THRESHOLD;
})();

const payBox = document.getElementById("payOptions");
const payThresholdInput = document.getElementById("payThreshold");
payThresholdInput.value = String(PAY_THRESHOLD);
payThresholdInput.addEventListener("input", () => {
  const v = parseFloat(payThresholdInput.value);
  PAY_THRESHOLD = Number.isFinite(v) && v >= 0 ? v : 0;
  localStorage.setItem(THRESHOLD_KEY, String(PAY_THRESHOLD));
  updatePayOptions(grandTotal());
});

payBox.addEventListener("click", e => {
  const opt = e.target.closest(".pay-opt");
  if (!opt || opt.classList.contains("disabled")) return;
  payBox.querySelectorAll(".pay-opt").forEach(o => o.classList.remove("active"));
  opt.classList.add("active");
  state.pay = opt.dataset.pay;
  calc();
});

function updatePayOptions(total) {
  const opts = payBox.querySelectorAll(".pay-opt");
  const note = document.getElementById("payNote");
  const below = total < PAY_THRESHOLD;
  opts.forEach(o => {
    const isFull = o.dataset.pay === "full";
    const restricted = below && !isFull;
    o.classList.toggle("disabled", restricted);
    if (restricted) {
      o.classList.remove("active");
      if (state.pay === o.dataset.pay) state.pay = "full";
    }
  });
  if (below) {
    state.pay = "full";
    opts[0].classList.add("active");
    note.textContent = `当前总金额 ${fmt(total)} 元 ＜ ${fmt0(PAY_THRESHOLD)} 元，未达到预付款起订金额，只能全额付款。`;
    note.classList.add("show");
  } else if (total > 0) {
    if (!state.pay) state.pay = "p30";
    opts.forEach(o => o.classList.toggle("active", o.dataset.pay === state.pay));
    note.textContent = `当前总金额 ${fmt(total)} 元 ≥ ${fmt0(PAY_THRESHOLD)} 元，可选择 30% 或 50% 预付款方式。`;
    note.classList.add("show");
  } else {
    note.classList.remove("show");
  }
  const td = document.getElementById("payDetail");
  const t = grandTotal();
  if (!t) { td.textContent = ""; return; }
  const map = { full: "全额付款", p30: "30%预付+70%尾款", p50: "50%预付+50%尾款" };
  const mode = map[state.pay] || "";
  if (state.pay === "p30") td.textContent = `付款方案：预付款 ¥${fmt(t*0.3)}（30%），尾款 ¥${fmt(t*0.7)}（70%）`;
  else if (state.pay === "p50") td.textContent = `付款方案：预付款 ¥${fmt(t*0.5)}（50%），尾款 ¥${fmt(t*0.5)}（50%）`;
  else td.textContent = `付款方案：${mode} ¥${fmt(t)}`;
}

// ============ 图片预览 ============
function showImg(src) {
  document.getElementById("modalImg").src = src;
  document.getElementById("imgModal").classList.add("show");
}

// ============ DOCX 生成器（图片以二进制内嵌，导出后即使换电脑也不丢图）============
