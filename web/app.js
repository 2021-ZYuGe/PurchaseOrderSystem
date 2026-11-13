// 采购下单系统 前端逻辑
let state = {
  supplier: null,          // {id, 供应商名称, 电话}
  items: [],               // {key, 产品名称, 规格, 图片, 单价, 数量}
  pay: null,               // full / p30 / p50
};

const norm = s => (s||"").toLowerCase().replace(/\s+/g,"");
const fmt = n => n.toLocaleString("zh-CN", {minimumFractionDigits:2, maximumFractionDigits:2});
const fmt0 = n => Number(n).toLocaleString("zh-CN", {maximumFractionDigits:0});

// 新增产品的默认备注
const DEFAULT_REMARK = "以上价格含13%专票+运费";

// 产品匹配：主名称 + 别名 + 规格 都能命中
function prodHit(p, q) {
  if (norm(p.产品名称).includes(q)) return true;
  if ((p.别名 || []).some(a => norm(a).includes(q))) return true;
  if (q.length >= 2 && norm(p.规格).includes(q)) return true;
  return false;
}
// 关键字高亮
function hl(text, q) {
  if (!q || !text) return text || "";
  const t = String(text);
  const i = norm(t).indexOf(q);
  if (i < 0) return t;
  return t.slice(0, i) + "<mark>" + t.slice(i, i + q.length) + "</mark>" + t.slice(i + q.length);
}

// ============ 供应商选择 ============
const supInput = document.getElementById("supInput");
const supResults = document.getElementById("supResults");

supInput.addEventListener("input", () => {
  const q = norm(supInput.value);
  // 输入框文字已和已选供应商不一致（含整段删除）→ 视为取消选择，
  // 同步收起「已选供应商」和「已有主合同」提示，避免旧供应商信息残留
  if (state.supplier && norm(state.supplier.供应商名称) !== q) clearSupplier();
  if (!q) { supResults.classList.remove("show"); return; }
  const list = SUPPLIERS.filter(s => norm(s.供应商名称).includes(q)).slice(0, 12);
  renderResults(supResults, list, s => ({
    t: s.供应商名称,
    d: `产品 ${s["产品keys"].length} 个`
      + (s.电话 ? ` · 电话 ${s.电话}` : "")
      + (s.最近签约日期
          ? ` · 最近签约 ${s.最近签约日期}`
          : " · 无历史签约记录"),
  }), item => {
    selectSupplier(item);
  });
});

function renderResults(box, list, fmtFn, onPick) {
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<div class="sr-item"><div class="d">无匹配结果</div></div>';
  } else {
    list.forEach(item => {
      const f = fmtFn(item);
      const div = document.createElement("div");
      div.className = "sr-item";
      div.innerHTML = `<div class="t">${f.t}</div><div class="d">${f.d}</div>`;
      div.onclick = () => { onPick(item); box.classList.remove("show"); };
      box.appendChild(div);
    });
  }
  box.classList.add("show");
}

document.addEventListener("click", e => {
  if (!e.target.closest(".search-box")) {
    supResults.classList.remove("show");
    prodResults.classList.remove("show");
  }
});

function selectSupplier(s) {
  state.supplier = s;
  supInput.value = s.供应商名称;
  try { sessionStorage.setItem("lastSupplier", s.供应商名称); } catch (e) {}
  document.getElementById("supInfo").style.display = "";
  document.getElementById("supName").textContent = s.供应商名称;
  document.getElementById("supProdCount").textContent = `产品 ${s["产品keys"].length} 个`;
  document.getElementById("supTel").textContent = s.电话 ? `📞 ${s.电话}` : "";
  renderContractStatus(s);
  document.getElementById("cardProduct").style.display = "";
  prodInput.focus();
}

// 取消供应商选择：已选供应商、主合同提示、空的产品区一并收起
function clearSupplier() {
  state.supplier = null;
  document.getElementById("supInfo").style.display = "none";
  hideContractBox();
  if (!state.items.length) document.getElementById("cardProduct").style.display = "none";
}

// 主合同提示框是异步渲染的，清空时必须连内容一起清掉，否则下次会闪旧数据
function hideContractBox() {
  const box = document.getElementById("contractBox");
  if (!box) return;
  box.style.display = "none";
  box.innerHTML = "";
}

// ============ 主合同状态提示 ============
const CONTRACT_STATUS = { data: null };

function cnDate(s) {
  const p = String(s || "").split("-");
  if (p.length !== 3 || !p[0]) return String(s || "");
  return `${p[0]}年${parseInt(p[1], 10)}月${parseInt(p[2], 10)}日`;
}

// 数据新鲜度：数据库更新到哪天、来源目录里还有没有没导入的新合同
function loadContractStatus() {
  const done = j => {
    if (!j || !j.ok) return;
    CONTRACT_STATUS.data = j.data || null;
    renderStat();
    if (state.supplier) renderContractStatus(state.supplier);
  };
  try {
    fetch("/api/contract_status", { cache: "no-store" })
      .then(r => r.json()).then(done).catch(() => {});
  } catch (e) {}
}

function freshnessHtml() {
  const st = CONTRACT_STATUS.data;
  if (!st) return "";
  const fresh = st.freshness || {};
  const pending = st.pending || {};
  const rows = [];
  const updated = String(fresh.数据更新时间 || "").slice(0, 16);
  if (updated) {
    rows.push(`数据库更新于 <b>${updated}</b> · 合同台账 ${fresh.合同记录 || 0} 份`);
  }
  if (pending.待导入数量 > 0) {
    rows.push(`<span class="warn">⚠ 发现 ${pending.待导入数量} 份新合同还没导入</span>`
      + (pending.最新日期 ? `（最新 ${String(pending.最新日期).slice(0, 10)}）` : ""));
    rows.push(`<div class="cb-actions">`
      + `<button class="cb-btn" id="btnSync" onclick="startSync()">立即更新</button>`
      + `<span class="cb-msg" id="syncMsg">解析后直接写入数据库，完成会自动刷新</span></div>`);
  } else if ((pending.不可用目录 || []).length) {
    const bad = (pending.不可用目录 || [])[0] || "";
    const drive = (bad.match(/^[A-Za-z]:/) || [""])[0].replace(":", "");
    rows.push(`<span class="muted">${drive ? drive + " 盘" : "合同来源目录"}未连接，暂时无法核对是否有更新的合同。</span>`);
  } else if (pending.检查时间) {
    rows.push(`<span class="ok">已核对合同来源目录，没有未导入的新合同。</span>`);
  }
  if (!rows.length) return "";
  return `<div class="cb-meta">${rows.join("<br>")}</div>`;
}

function setSyncMsg(text) {
  const el = document.getElementById("syncMsg");
  if (el) el.textContent = text;
}

// 页面一键更新：把扫描到的新合同解析并写入数据库
function startSync() {
  const btn = document.getElementById("btnSync");
  if (btn) { btn.disabled = true; btn.textContent = "正在更新…"; }
  setSyncMsg("正在启动…");
  fetch("/api/sync_contracts", { method: "POST" })
    .then(r => r.json())
    .then(j => {
      if (!j || !j.ok) {
        setSyncMsg((j && j.error) || "启动失败");
        if (btn) { btn.disabled = false; btn.textContent = "立即更新"; }
        return;
      }
      setSyncMsg(`正在处理 ${j.total || 0} 份合同，解析需要一点时间…`);
      pollSync();
    })
    .catch(() => {
      setSyncMsg("连接服务失败，请确认系统正在运行");
      if (btn) { btn.disabled = false; btn.textContent = "立即更新"; }
    });
}

function pollSync() {
  fetch("/api/sync_status", { cache: "no-store" })
    .then(r => r.json())
    .then(j => {
      const d = (j && j.data) || {};
      if (d.state === "running") {
        setSyncMsg(d.message || "正在解析合同…");
        setTimeout(pollSync, 1500);
        return;
      }
      if (d.state === "done") {
        setSyncMsg("更新完成，正在刷新页面…");
        setTimeout(() => location.reload(), 900);
        return;
      }
      if (d.state === "error") {
        setSyncMsg("更新失败：" + (d.message || "未知错误"));
        const btn = document.getElementById("btnSync");
        if (btn) { btn.disabled = false; btn.textContent = "重试"; }
        return;
      }
      setTimeout(pollSync, 1500);
    })
    .catch(() => setTimeout(pollSync, 2000));
}

function renderContractStatus(s) {
  const box = document.getElementById("contractBox");
  if (!box) return;
  const main = s.主合同日期 || "";
  const latest = s.最近签约日期 || main;
  const latestNo = s.最近合同号 || "";
  const records = Number(s.合同记录数 || 0);
  const parsedCount = Number(s.历史合同份数 || 0);
  const count = records || parsedCount;
  const html = [];
  // 合同到期：读自合同正文的期限，或预警面板里手工登记的日期
  const ex = expiryOf(s.供应商名称);
  const exDays = (ex && ex.到期日)
    ? (ex.剩余天数 != null ? ex.剩余天数 : daysLeft(ex.到期日))
    : null;
  const exBucket = (ex && ex.到期日) ? (ex.档位 || bucketOf(exDays)) : "";
  const exMeta = BUCKET_META[exBucket] || BUCKET_META.unknown;

  if (main) {
    html.push(`<div class="cb-title">✓ 已有主合同<span class="cb-sub"`
      + ` title="按合同台账统计：一份合同算一份，同一合同在多个文件夹里的副本不重复计数">`
      + `共 ${count} 份历史合同</span></div>`);
    html.push(`<div class="cb-line">最近签约：<b>${cnDate(latest || main)}</b>`
      + (latestNo ? ` · ${latestNo}` : "") + `</div>`);
    if (ex && ex.到期日) {
      const left = exDays < 0 ? `已过期 ${-exDays} 天`
        : (exDays === 0 ? "今天到期" : `${exMeta.label} · 剩 ${exDays} 天`);
      html.push(`<div class="cb-line">合同有效期：${ex.起始日 ? cnDate(ex.起始日) + " 至 " : "至 "}`
        + `<b>${cnDate(ex.到期日)}</b>`
        + `<span class="cb-tag" style="color:${exMeta.color};background:${exMeta.bg}">${left}</span>`
        + (ex.待确认 ? `<span class="cb-tag" style="color:#6a1b9a;background:#f3e5f5" title="最近一份合同的正文没有写明期限">需核对</span>` : "")
        + `</div>`);
    } else if (count) {
      html.push(`<div class="cb-line">合同期限：<span style="color:#8a5a00">未登记到期日</span>`
        + ` <a href="javascript:;" class="cb-link" onclick="openExpiry('unknown')">去登记</a>`
        + `<span class="cb-sub">（老合同正文没有期限条款时需手工补）</span></div>`);
    }
    html.push(`<div class="hint">日期取自合同正文“已于…签订《购销框架合同》”一句。本次下单只需出《产品订购清单》，清单内自动引用该日期，无需重复签约主体合同。</div>`);
    box.style.background = "#e8f5e9";
    box.style.color = "#1b5e20";
  } else if (count) {
    html.push(`<div class="cb-title">有 ${count} 份历史合同，但未识别到主合同日期</div>`);
    if (latest) html.push(`<div class="cb-line">最近签约：<b>${cnDate(latest)}</b>${latestNo ? ` · ${latestNo}` : ""}</div>`);
    html.push(`<div class="hint">《产品订购清单》的主合同日期会留空，建议确认后再下单。</div>`);
    box.style.background = "#fff8e1";
    box.style.color = "#8a5a00";
  } else {
    html.push(`<div class="cb-title">该供应商走月结模式（无框架合同）</div>`);
    html.push(`<div class="hint">此类按月度对账结算，无需签订主合同。本次仍可正常下单，《产品订购清单》中的主合同日期留空即可。</div>`);
    box.style.background = "#eef4fc";
    box.style.color = "#1a5fb4";
  }
  // 到期很紧时整卡改成红底，压过“已有主合同”的绿色，避免看着像没事
  if (exDays !== null && exDays <= 7) {
    box.style.background = "#fdecea";
    box.style.color = "#8c1d18";
  }
  html.push(freshnessHtml());
  box.innerHTML = html.join("");
  box.style.display = "block";
}

// ============ 合同到期预警 ============
// 分档口径：3 天 / 1 周 / 1 个月 / 3 个月 / 6 个月，和服务端 sqlite_store 保持一致。
// 剩余天数在浏览器里按今天重算，页面开着跨天也不会显示旧数字。
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

// ============ 产品搜索 ============
const prodInput = document.getElementById("prodInput");
const prodResults = document.getElementById("prodResults");

prodInput.addEventListener("input", () => {
  const raw = prodInput.value.trim();
  const q = norm(raw);
  if (!q) { prodResults.classList.remove("show"); return; }
  const supKeys = new Set(state.supplier ? state.supplier["产品keys"] : []);
  const matches = PRODUCTS.filter(p => prodHit(p, q));
  // 供应商产品优先，其次有图的优先
  matches.sort((a, b) =>
    (supKeys.has(b.id)?1:0) - (supKeys.has(a.id)?1:0) ||
    (b.图片?1:0) - (a.图片?1:0) ||
    b.下单次数 - a.下单次数
  );
  const list = matches.slice(0, 20);
  renderResults(prodResults, list, p => {
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
});

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


// ============ 初始化统计 ============
function renderStat() {
  const fresh = (CONTRACT_STATUS.data && CONTRACT_STATUS.data.freshness) || {};
  const updated = String(fresh.数据更新时间 || "").slice(0, 10);
  const extra = updated ? ` · 数据更新 ${updated}` : "";
  document.getElementById("statInfo").textContent =
    `产品库 ${PRODUCTS.length} 项 · 供应商 ${SUPPLIERS.length} 家 · 图片 ${PRODUCTS.filter(p=>p.图片).length} 张${extra}`;
}
renderStat();
renderItems();
// 一键更新后页面会刷新，恢复刚才选中的供应商
try {
  const last = sessionStorage.getItem("lastSupplier");
  if (last) {
    const saved = SUPPLIERS.find(x => x.供应商名称 === last);
    if (saved) selectSupplier(saved);
  }
} catch (e) {}
loadContractStatus();
loadExpiry();
// 支持 ?expiry=1 直接打开预警面板（方便做桌面快捷方式）
try {
  if (/[?&]expiry=1/.test(location.search)) setTimeout(() => openExpiry(), 400);
} catch (e) {}
