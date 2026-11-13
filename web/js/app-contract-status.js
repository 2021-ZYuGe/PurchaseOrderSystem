// contract-status
// 数据新鲜度、一键更新、供应商主合同提示。

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
