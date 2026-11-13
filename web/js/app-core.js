// core
// 全局状态、工具函数、供应商选择与基础渲染。
// 注意：这些文件按顺序以经典脚本加载，顶层函数会挂到 window，
// 页面里的内联 onclick 依赖这一点，不要改成 ES module。

// 采购下单系统 前端逻辑
let state = {
  supplier: null,          // {id, 供应商名称, 电话}
  items: [],               // {key, 产品名称, 规格, 图片, 单价, 数量}
  pay: null,               // full / p30 / p50
};

// 目录数据由 /api/bootstrap 提供（P2 起不再加载 data.js）
let SUPPLIERS = window.SUPPLIERS || [];
const META = { products: 0, suppliers: 0, with_image: 0, updated: "" };

async function fetchJSON(url, opts) {
  const resp = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
  const text = await resp.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    throw new Error("服务返回异常（HTTP " + resp.status + "）");
  }
  if (!data || data.ok !== true) {
    throw new Error((data && data.error) || ("请求失败（HTTP " + resp.status + "）"));
  }
  return data.data;
}

const norm = s => (s||"").toLowerCase().replace(/\s+/g,"");
const fmt = n => n.toLocaleString("zh-CN", {minimumFractionDigits:2, maximumFractionDigits:2});
const fmt0 = n => Number(n).toLocaleString("zh-CN", {maximumFractionDigits:0});

// 新增产品的默认备注
const DEFAULT_REMARK = "以上价格含13%专票+运费";

// 产品匹配规则在后端 search_products()（名称 / 别名 / 2 字以上规格）
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
