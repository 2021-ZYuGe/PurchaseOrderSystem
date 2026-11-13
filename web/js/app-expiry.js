// expiry
// 合同到期预警：分档、面板、期限登记。

const EXPIRY = { data: null, filter: "all", editing: "" };

const BUCKET_META = {
  expired: { label: "已过期", color: "#b71c1c", bg: "#fdecea" },
  d3:      { label: "3 天内", color: "#b71c1c", bg: "#fdecea" },
  d7:      { label: "1 周内", color: "#e65100", bg: "#fff3e0" },
  d30:     { label: "1 个月内", color: "#b26a00", bg: "#fff8e1" },
  d90:     { label: "3 个月内", color: "#1565c0", bg: "#e8f1fb" },
  d180:    { label: "6 个月内", color: "#1b5e20", bg: "#e8f5e9" },
  ok:      { label: "6 个月以上", color: "#1b5e20", bg: "#e8f5e9" },
  pending: { label: "待确认", color: "#6a1b9a", bg: "#f3e5f5" },
  unknown: { label: "未登记", color: "#5f6b7a", bg: "#f0f2f5" },
};

function todayISO() {
  const d = new Date();
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function daysLeft(iso) {
  if (!iso) return null;
  const a = new Date(String(iso).slice(0, 10) + "T00:00:00");
  const b = new Date(todayISO() + "T00:00:00");
  if (isNaN(a.getTime())) return null;
  return Math.round((a - b) / 86400000);
}

function bucketOf(days) {
  if (days === null || days === undefined) return "unknown";
  if (days < 0) return "expired";
  if (days <= 3) return "d3";
  if (days <= 7) return "d7";
  if (days <= 30) return "d30";
  if (days <= 90) return "d90";
  if (days <= 180) return "d180";
  return "ok";
}

function loadExpiry() {
  try {
    fetch("/api/contract_expiry", { cache: "no-store" })
      .then(r => r.json())
      .then(j => {
        if (!j || !j.ok || !j.data) return;
        EXPIRY.data = j.data;
        renderExpiryBadge();
        renderExpiryBar();
        if (document.getElementById("expiryModal").classList.contains("show")) renderExpiryRows();
        if (state.supplier) renderContractStatus(state.supplier);
      })
      .catch(() => {});
  } catch (e) {}
}

// 从别的页面切回来时重新算一次，避免放了一夜还显示昨天的天数
document.addEventListener("visibilitychange", function () {
  if (!document.hidden) loadExpiry();
});

function renderExpiryBadge() {
  const el = document.getElementById("expiryBadge");
  if (!el) return;
  const c = (EXPIRY.data && EXPIRY.data.counts) || {};
  const n = (c.d3 || 0) + (c.d7 || 0) + (c.d30 || 0);
  el.textContent = n > 99 ? "99+" : String(n);
  el.style.display = n ? "block" : "none";
  el.title = `1 个月内到期 ${n} 家`;
}

function renderExpiryBar() {
  const el = document.getElementById("expiryBar");
  if (!el) return;
  const data = EXPIRY.data;
  if (!data || !data.counts) { el.style.display = "none"; return; }
  const c = data.counts;
  const urgent = (c.expired || 0) + (c.d3 || 0) + (c.d7 || 0);
  const soon = (c.d30 || 0) + (c.d90 || 0);
  if (!urgent && !soon) { el.style.display = "none"; return; }
  const parts = [];
  if (c.expired) parts.push(`已过期 <b>${c.expired}</b> 家`);
  if (c.d3) parts.push(`<b>${c.d3}</b> 家 3 天内到期`);
  if (c.d7) parts.push(`<b>${c.d7}</b> 家 1 周内到期`);
  if (c.d30) parts.push(`<b>${c.d30}</b> 家 1 个月内到期`);
  if (c.d90) parts.push(`<b>${c.d90}</b> 家 3 个月内到期`);
  el.className = "expiry-bar" + (urgent ? " urgent" : "");
  el.innerHTML = `<div class="eb-main">⏰ 合同到期：${parts.join(" · ")}`
    + `<span style="opacity:.7">（共 ${data.total} 家供应商，数据截至 ${data.today}）</span></div>`
    + `<button type="button" class="eb-btn" onclick="openExpiry()">查看并处理</button>`;
  el.style.display = "flex";
}

function openExpiry(filter) {
  EXPIRY.filter = filter || "all";
  const search = document.getElementById("expirySearch");
  if (search) search.value = "";
  document.getElementById("expiryModal").classList.add("show");
  renderExpiryRows();
  loadExpiry();
}

function closeExpiry() {
  document.getElementById("expiryModal").classList.remove("show");
}

function renderExpiryTabs() {
  const box = document.getElementById("expiryTabs");
  if (!box) return;
  const data = EXPIRY.data;
  if (!data) { box.innerHTML = ""; return; }
  const c = data.counts || {};
  const order = ["all", "expired", "d3", "d7", "d30", "d90", "d180", "ok", "pending", "unknown"];
  const tabs = order.filter((k, i) => {
    if (k === "all") return true;
    if (k === "unknown") return true;
    return (c[k] || 0) > 0;
  }).map(k => {
    const n = k === "all" ? (data.total || 0) : (c[k] || 0);
    const label = k === "all" ? "全部" : (BUCKET_META[k] ? BUCKET_META[k].label : k);
    return `<button type="button" class="exp-tab${EXPIRY.filter === k ? " active" : ""}" `
      + `onclick="switchExpiryTab('${k}')">${label}<span class="n">${n}</span></button>`;
  });
  box.innerHTML = tabs.join("");
}

function switchExpiryTab(key) {
  EXPIRY.filter = key;
  renderExpiryRows();
}

function renderExpiryRows() {
  const body = document.getElementById("expiryBody");
  if (!body) return;
  renderExpiryTabs();
  const data = EXPIRY.data;
  if (!data) { body.innerHTML = '<div class="exp-empty">正在读取合同数据…</div>'; return; }
  const input = document.getElementById("expirySearch");
  const q = norm(input ? input.value.trim() : "");
  const list = (data.items || []).filter(it => {
    if (EXPIRY.filter !== "all" && it.档位 !== EXPIRY.filter) return false;
    if (q && norm(it.供应商).indexOf(q) < 0) return false;
    return true;
  });
  if (!list.length) {
    body.innerHTML = '<div class="exp-empty">这个分类下没有供应商</div>';
    return;
  }
  const rows = list.map(it => {
    const dl = daysLeft(it.到期日);
    const bucket = it.档位 || bucketOf(dl);
    const meta = BUCKET_META[bucket] || BUCKET_META.unknown;
    const dayText = it.到期日
      ? (dl < 0 ? `已过期 ${-dl} 天` : (dl === 0 ? "今天到期" : `剩 ${dl} 天`))
      : "—";
    const srcText = it.来源 === "manual" ? "手工登记"
      : (it.来源 === "contract" ? "合同正文"
        : (it.合同份数 ? "合同未写期限" : "无框架合同"));
    const no = it.合同号 || "";
    const title = it.合同文件 ? ` title="${it.合同文件}"` : "";
    const noCell = (no || srcText || "—")
      + (no && srcText ? `<br><span style="font-size:11px">${srcText}</span>` : "");
    return `<tr>
      <td class="sup">${it.供应商}${it.待确认 ? '<span class="cb-tag" style="color:#6a1b9a;background:#f3e5f5" title="最近一份合同的正文没有写明期限，系统无法判断是否已续签">需核对</span>' : ""}
        ${it.最近签约 ? `<small>最近签约 ${it.最近签约}</small>` : ""}</td>
      <td class="date">${it.到期日 ? cnDate(it.到期日) : '<span style="color:#a0a8b4">未登记</span>'}</td>
      <td class="days" style="color:${meta.color}">${dayText}</td>
      <td>${bucket === "unknown" ? "" : `<span class="cb-tag" style="color:${meta.color};background:${meta.bg};margin-left:0">${meta.label}</span>`}</td>
      <td class="no"${title}>${noCell}</td>
      <td class="ops">
        <button type="button" class="op" onclick="openTermEditor('${jsStr(it.供应商)}')">${it.到期日 ? "修改" : "登记"}</button>
        <a class="op plain" href="/contract.html" target="_blank" rel="noopener">续签</a>
      </td>
    </tr>`;
  });
  body.innerHTML = `<table class="exp-table">
    <thead><tr><th>供应商</th><th style="width:118px">到期日</th><th style="width:104px">剩余</th>
    <th style="width:92px">预警</th><th style="width:118px">合同号 / 来源</th><th style="width:104px"></th></tr></thead>
    <tbody>${rows.join("")}</tbody></table>`;
}

// 供应商名里可能带引号，拼进 onclick 前先转义
function jsStr(text) {
  return String(text || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "&quot;");
}

function expiryOf(name) {
  const data = EXPIRY.data;
  if (data && data.items) {
    const hit = data.items.find(x => x.供应商 === name);
    if (hit) return hit;
  }
  const s = SUPPLIERS.find(x => x.供应商名称 === name);
  if (s && s.合同截止日期) {
    const dl = daysLeft(s.合同截止日期);
    return {
      供应商: name, 到期日: s.合同截止日期, 起始日: s.合同起始日期 || "",
      剩余天数: dl, 档位: bucketOf(dl), 合同号: s.到期合同号 || "",
      来源: s.期限来源 || "", 待确认: !!s.期限待确认,
    };
  }
  return null;
}

function openTermEditor(name) {
  const it = expiryOf(name) || {};
  EXPIRY.editing = name;
  document.getElementById("termSub").textContent = name;
  document.getElementById("termStart").value = it.起始日 || "";
  document.getElementById("termEnd").value = it.到期日 || "";
  document.getElementById("termNote").value = it.备注 || "";
  document.getElementById("termDelete").style.display = (it.来源 === "manual") ? "inline-block" : "none";
  const msg = document.getElementById("termMsg");
  msg.style.color = "#5f6b7a";
  msg.textContent = it.来源 === "contract"
    ? "当前到期日读自合同正文。手工登记会取两者中较晚的日期，续签后自动更新。"
    : "";
  document.getElementById("termModal").classList.add("show");
}

function closeTermEditor() {
  document.getElementById("termModal").classList.remove("show");
  EXPIRY.editing = "";
}

function submitTerm() {
  const name = EXPIRY.editing;
  const start = document.getElementById("termStart").value.trim();
  const end = document.getElementById("termEnd").value.trim();
  const note = document.getElementById("termNote").value.trim();
  const msg = document.getElementById("termMsg");
  if (!name) return;
  if (!end) { msg.style.color = "#c62828"; msg.textContent = "请填写到期日期"; return; }
  if (start && end < start) { msg.style.color = "#c62828"; msg.textContent = "到期日期不能早于起始日期"; return; }
  const btn = document.getElementById("termSave");
  btn.disabled = true; btn.textContent = "保存中…";
  fetch("/api/save_contract_term", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 供应商: name, 起始日: start, 到期日: end, 备注: note }),
  })
    .then(r => r.json())
    .then(j => {
      if (!j || !j.ok) throw new Error((j && j.error) || "保存失败");
      if (j.overview) EXPIRY.data = j.overview;
      closeTermEditor();
      renderExpiryBadge(); renderExpiryBar(); renderExpiryRows();
      if (state.supplier) renderContractStatus(state.supplier);
    })
    .catch(e => {
      msg.style.color = "#c62828";
      msg.textContent = String(e.message || e);
    })
    .finally(() => { btn.disabled = false; btn.textContent = "保存"; });
}

function deleteTerm() {
  const name = EXPIRY.editing;
  if (!name) return;
  if (!confirm(`撤销「${name}」的手工期限登记？\n撤销后按合同正文里写的期限计算。`)) return;
  const msg = document.getElementById("termMsg");
  fetch("/api/delete_contract_term", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 供应商: name }),
  })
    .then(r => r.json())
    .then(j => {
      if (!j || !j.ok) throw new Error((j && j.error) || "撤销失败");
      if (j.overview) EXPIRY.data = j.overview;
      closeTermEditor();
      renderExpiryBadge(); renderExpiryBar(); renderExpiryRows();
      if (state.supplier) renderContractStatus(state.supplier);
    })
    .catch(e => { msg.style.color = "#c62828"; msg.textContent = String(e.message || e); });
}

// ============ 产品搜索（服务端按需查询，不再本地过滤全量） ============
