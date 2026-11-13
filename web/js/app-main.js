// main
// 页面初始化：拉取目录、恢复上次供应商、启动轮询。

// ============ 初始化：先拉目录，再渲染 ============
function renderStat() {
  const fresh = (CONTRACT_STATUS.data && CONTRACT_STATUS.data.freshness) || {};
  const updated = String(META.updated || fresh.数据更新时间 || "").slice(0, 10);
  const extra = updated ? ` · 数据更新 ${updated}` : "";
  document.getElementById("statInfo").textContent =
    `产品库 ${META.products} 项 · 供应商 ${META.suppliers} 家 · 图片 ${META.with_image} 张${extra}`;
}

function restoreLastSupplier() {
  // 一键更新后页面会刷新，恢复刚才选中的供应商
  try {
    const last = sessionStorage.getItem("lastSupplier");
    if (!last) return;
    const saved = SUPPLIERS.find(x => x.供应商名称 === last);
    if (saved) selectSupplier(saved);
  } catch (e) {}
}

async function bootstrap() {
  const stat = document.getElementById("statInfo");
  if (stat) stat.textContent = "正在加载产品库…";
  try {
    const data = await fetchJSON("/api/bootstrap");
    const meta = data.meta || {};
    META.products = meta.products || 0;
    META.suppliers = meta.suppliers || 0;
    META.with_image = meta.with_image || 0;
    META.updated = meta.updated || "";
    SUPPLIERS = data.suppliers || [];
    renderStat();
    restoreLastSupplier();
    if (!META.products && window.__guide) window.__guide();
  } catch (e) {
    if (stat) stat.textContent = "产品库加载失败";
    if (window.__showGuide) {
      window.__showGuide("<b>读取不到产品库</b>　请确认系统服务正常，或运行「工具 / 更新数据源.py」导入合同。"
        + '<button onclick="location.reload()" style="margin-left:12px;padding:8px 20px;font-size:15px;'
        + 'border:none;border-radius:6px;background:#fff;color:#c0392b;cursor:pointer;font-weight:700">重新加载</button>');
    }
  }
}

renderItems();
bootstrap();
loadContractStatus();
loadExpiry();
// 支持 ?expiry=1 直接打开预警面板（方便做桌面快捷方式）
try {
  if (/[?&]expiry=1/.test(location.search)) setTimeout(() => openExpiry(), 400);
} catch (e) {}
