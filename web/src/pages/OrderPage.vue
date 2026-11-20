<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import SearchSelect from '../components/SearchSelect.vue'
import ProductSearch from '../components/ProductSearch.vue'
import OrderTable from '../components/OrderTable.vue'
import PayModePicker from '../components/PayModePicker.vue'
import { useCatalog } from '../composables/useCatalog'
import { usePayThreshold } from '../composables/usePayThreshold'
import { useExpiry } from '../composables/useExpiry'
import { useToast } from '../composables/useToast'
import {
  DEFAULT_REMARK,
  buildMainContractDocx,
  buildOrderDocx,
  downloadDocx,
  payModeLabel,
} from '../lib/order-docs'
import { loadPartyA, pickPartyA, rememberPartyA, selectedPartyAName } from '../lib/party-a'
import { savePartyA } from '../api/catalog'
import {
  fetchContractStatus,
  fetchSyncStatus,
  startSync as runSync,
} from '../api/contracts'
import { amountCents, cnDate, formatCents, formatMoney0 } from '../lib/format'

const { findSuppliers, loadMeta } = useCatalog()
const { threshold, setThreshold } = usePayThreshold()
const { expiry, load: loadExpiry } = useExpiry()
const { notify, error: toastError, success: toastSuccess } = useToast()
const router = useRouter()

const supplier = ref(null)
const partyAList = ref([])
const partyA = ref(null)
const items = ref([])
const payMode = ref('')
const exported = ref(false)
const productSearchKey = ref(0)
const supplierKeyVersion = ref(0)
const exporting = ref(false)
const exportHint = ref('')
const previewImage = ref('')
const resetArmed = ref(false)
const contractStatus = ref(null)
const statusError = ref('')
const syncing = ref(false)
const syncMessage = ref('')

let resetTimer = null
let syncTimer = null

const BUCKET_META = {
  expired: { label: '已过期', color: '#b71c1c', bg: '#fdecea' },
  d3: { label: '3 天内', color: '#b71c1c', bg: '#fdecea' },
  d7: { label: '1 周内', color: '#e65100', bg: '#fff3e0' },
  d30: { label: '1 个月内', color: '#b26a00', bg: '#fff8e1' },
  d90: { label: '3 个月内', color: '#1565c0', bg: '#e8f1fb' },
  d180: { label: '6 个月内', color: '#1b5e20', bg: '#e8f5e9' },
  ok: { label: '6 个月以上', color: '#1b5e20', bg: '#e8f5e9' },
  pending: { label: '待确认', color: '#6a1b9a', bg: '#f3e5f5' },
  unknown: { label: '未登记', color: '#5f6b7a', bg: '#f0f2f5' },
}

async function searchSuppliers(q) {
  const list = await findSuppliers(q)
  return list.slice(0, 12)
}

function supplierTitle(s) {
  return s.name
}

function supplierDetail(s) {
  const count = (s.product_ids || []).length
  let text = `产品 ${count} 个`
  if (s.phone) text += ` · 电话 ${s.phone}`
  text += s.latest_sign_date ? ` · 最近签约 ${s.latest_sign_date}` : ' · 无历史签约记录'
  return text
}

function supplierKey(s) {
  return s.id || s.name
}

function setSupplier(value) {
  supplier.value = value || null
  try {
    if (value) sessionStorage.setItem('lastSupplier', JSON.stringify(value))
    else sessionStorage.removeItem('lastSupplier')
  } catch (e) {
    /* 忽略 */
  }
}

function clearOrder() {
  items.value = []
  payMode.value = ''
  exported.value = false
  productSearchKey.value += 1
}

function autoPickParty(next) {
  if (!next || !partyA.value) return
  const rows = (next.parties || []).filter(
    (row) => row.party_a && (row.contract_count || 0) > 0,
  )
  if (!rows.length) return
  if (rows.some((row) => row.party_a === partyA.value.name)) return
  const target = [...rows].sort(
    (a, b) => String(b.latest_sign || '').localeCompare(String(a.latest_sign || '')),
  )[0]
  const info = partyAList.value.find((item) => item.name === target.party_a)
  if (info) {
    partyA.value = info
    rememberPartyA(info.name)
  }
}

function onSupplierChange(value, explicit = false) {
  // 搜索框里改字会先发一次 null，不能当成“取消选择”
  if (!value && !explicit) return
  const next = value || null
  const current = supplier.value && supplier.value.name
  if (current === (next && next.name)) return
  if (items.value.length) {
    // 已导出视为一单结束，直接清空；未导出则每次切换都提醒
    if (!exported.value) {
      const text = '换供应商会清空已选产品、单价和付款方式，继续？'
      if (!window.confirm(text)) {
        supplierKeyVersion.value += 1
        return
      }
    }
    clearOrder()
  }
  setSupplier(next)
  autoPickParty(next)
}

function onSupplierEdit() {
  if (!items.value.length) return
  if (exported.value) {
    clearOrder()
    return
  }
  const text = '换供应商会清空已选产品、单价和付款方式，继续？'
  if (!window.confirm(text)) {
    supplierKeyVersion.value += 1
    return
  }
  clearOrder()
}

function restoreSupplier() {
  try {
    const raw = sessionStorage.getItem('lastSupplier')
    if (!raw) return
    const saved = JSON.parse(raw)
    if (saved && saved.name) supplier.value = saved
  } catch (e) {
    /* 忽略 */
  }
}

function addProduct(product) {
  if (items.value.some((it) => it.id === product.id)) {
    notify('该产品已在清单中')
    return
  }
  const images = [product.image, ...(product.images || [])]
    .filter(Boolean)
    .filter((value, index, arr) => arr.indexOf(value) === index)
  const prices = product.prices || []
  exported.value = false
  items.value.push({
    id: product.id,
    name: product.name,
    spec: product.spec || '',
    image: images[0] || '',
    images,
    unitPrice: prices.length ? String(prices[0]) : '',
    qty: '',
    remark: DEFAULT_REMARK,
    historyPrices: prices,
  })
}

function updateItem({ id, field, value }) {
  const item = items.value.find((it) => it.id === id)
  if (!item) return
  item[field] = value
  exported.value = false
}

function removeItem(id) {
  items.value = items.value.filter((it) => it.id !== id)
  exported.value = false
}

function cycleImage(id) {
  const item = items.value.find((it) => it.id === id)
  if (!item || item.images.length < 2) return
  const index = item.images.indexOf(item.image)
  item.image = item.images[(index + 1) % item.images.length]
  exported.value = false
}

const totalCents = computed(() =>
  items.value.reduce((sum, item) => sum + amountCents(item.unitPrice, item.qty), 0),
)

const supplierParties = computed(() => (supplier.value && supplier.value.parties) || [])

const knownParties = computed(() => supplierParties.value.filter((row) => row.party_a))

const sortedParties = computed(() => [...knownParties.value].sort((a, b) => {
  const left = a.latest_sign || ''
  const right = b.latest_sign || ''
  if (left !== right) return right.localeCompare(left)
  return String(a.party_a_label).localeCompare(String(b.party_a_label))
}))

const contractTotal = computed(() => {
  const sum = supplierParties.value.reduce((total, row) => total + (row.contract_count || 0), 0)
  return sum || (supplier.value && supplier.value.contract_count) || 0
})

const latestParty = computed(
  () => sortedParties.value.find((row) => row.latest_sign) || null,
)

const selectedPartyRow = computed(
  () => supplierParties.value.find((row) => row.party_a === (partyA.value && partyA.value.name)) || null,
)

const selectedMainDate = computed(
  () => (selectedPartyRow.value && selectedPartyRow.value.latest_sign) || '',
)

const overallValidity = computed(() => {
  const rows = knownParties.value.filter((row) => row.end_date)
  if (!rows.length) return null
  return [...rows].sort((a, b) => String(b.end_date).localeCompare(String(a.end_date)))[0]
})

const unconfirmedCount = computed(
  () => supplierParties.value.filter((row) => !row.party_a).length,
)

const boxTone = computed(() => {
  const current = overallValidity.value
  if (current && current.days_left !== null && current.days_left !== undefined
    && current.days_left <= 7) return 'danger'
  if (knownParties.value.length) return 'ok'
  if (contractTotal.value) return 'warn'
  return 'info'
})

const partyAHint = computed(() => {
  if (!supplier.value || !partyA.value) return ''
  const row = selectedPartyRow.value
  if (row) {
    const date = row.latest_sign ? ` · 主合同日期 ${cnDate(row.latest_sign)}` : ''
    return `该甲方 ${row.contract_count || 0} 份合同${date}`
  }
  if (supplierParties.value.length) {
    return '该供应商没有这家甲方的合同，清单中的主合同日期将留空'
  }
  return '该供应商没有框架合同，清单中的主合同日期将留空'
})

const expiryCounts = computed(() => (expiry.value && expiry.value.counts) || {})
const expiryTotal = computed(() => (expiry.value && expiry.value.total) || 0)
const expirySupplierCount = computed(
  () => new Set(((expiry.value && expiry.value.items) || []).map((item) => item.supplier)).size,
)
const expiryDate = computed(() => (expiry.value && expiry.value.today) || '')
const expiryUrgent = computed(
  () => (expiryCounts.value.expired || 0) + (expiryCounts.value.d3 || 0) > 0,
)
const showExpiryBar = computed(() => expiryTotal.value > 0 && (
  (expiryCounts.value.expired || 0)
  + (expiryCounts.value.d3 || 0)
  + (expiryCounts.value.d7 || 0)
  + (expiryCounts.value.d30 || 0)
  + (expiryCounts.value.d90 || 0)
) > 0)

const freshness = computed(() => (contractStatus.value && contractStatus.value.freshness) || {})
const pendingInfo = computed(() => (contractStatus.value && contractStatus.value.pending) || {})
const freshnessVisible = computed(() => Boolean(contractStatus.value))

function tagStyle(row) {
  const meta = BUCKET_META[row.pending ? 'pending' : row.bucket] || BUCKET_META.unknown
  return { color: meta.color, background: meta.bg }
}

function tagText(row) {
  if (row.pending) return '需核对'
  if (!row.end_date) return '未登记'
  const days = row.days_left
  if (days === null || days === undefined) return '未登记'
  if (days < 0) return `已过期 ${-days} 天`
  if (days === 0) return '今天到期'
  const meta = BUCKET_META[row.bucket] || BUCKET_META.unknown
  return `${meta.label} · 剩 ${days} 天`
}

function removeSupplier() {
  onSupplierChange(null, true)
}

async function exportOrder() {
  if (exporting.value) return
  if (!supplier.value) {
    toastError('请先选择供应商')
    return
  }
  if (!partyA.value) {
    toastError('请先选择甲方')
    return
  }
  if (!items.value.length) {
    toastError('请先添加产品')
    return
  }
  if (!totalCents.value) {
    toastError('请填写单价和数量')
    return
  }
  if (!payMode.value) {
    toastError('请选择付款方式')
    return
  }
  if (!selectedPartyRow.value
    && !window.confirm('所选甲方没有该供应商的主合同记录，主合同日期将留空，是否继续？')) {
    return
  }
  exporting.value = true
  exportHint.value = '正在打包图片…'
  try {
    const result = await buildOrderDocx({
      supplier: supplier.value,
      items: items.value,
      payMode: payMode.value,
      totalCents: totalCents.value,
      partyA: partyA.value,
      mainContractDate: selectedMainDate.value,
    })
    exportHint.value = '正在生成 Word…'
    downloadDocx(result.blob, result.filename)
    exported.value = true
    toastSuccess('产品订购清单已生成，开始下载')
  } catch (e) {
    toastError('生成失败：' + (e && e.message ? e.message : e))
  } finally {
    exporting.value = false
    exportHint.value = ''
  }
}

function exportMainContract() {
  if (!supplier.value) {
    toastError('请先选择供应商')
    return
  }
  if (!partyA.value) {
    toastError('请先选择甲方')
    return
  }
  try {
    const result = buildMainContractDocx(supplier.value, threshold.value, partyA.value)
    downloadDocx(result.blob, result.filename)
    toastSuccess('购销框架合同已生成，开始下载')
  } catch (e) {
    toastError('生成失败：' + (e && e.message ? e.message : e))
  }
}

function resetAll() {
  if (!resetArmed.value) {
    resetArmed.value = true
    clearTimeout(resetTimer)
    resetTimer = setTimeout(() => {
      resetArmed.value = false
    }, 4000)
    return
  }
  clearTimeout(resetTimer)
  resetArmed.value = false
  clearOrder()
  removeSupplier()
  toastSuccess('已清空当前订单')
}

async function loadPartyList() {
  try {
    partyAList.value = await loadPartyA()
    partyA.value = pickPartyA(partyAList.value, selectedPartyAName())
    autoPickParty(supplier.value)
  } catch (e) {
    notify('甲方信息读取失败：' + (e && e.message ? e.message : e))
  }
}

async function refreshSupplier() {
  if (!supplier.value) return
  try {
    const list = await findSuppliers(supplier.value.name)
    const hit = list.find((item) => item.name === supplier.value.name)
    if (hit) {
      setSupplier(hit)
      autoPickParty(hit)
    }
  } catch (e) {
    /* 恢复上次供应商失败不打断页面 */
  }
}

watch(payMode, () => {
  exported.value = false
})

watch(partyA, (value) => {
  if (value) rememberPartyA(value.name)
  exported.value = false
})

function onPartyAChange() {
  if (partyA.value) rememberPartyA(partyA.value.name)
}

async function savePartyInfo() {
  if (!partyA.value || !partyA.value.name) return
  try {
    await savePartyA({ ...partyA.value })
    toastSuccess('甲方信息已保存')
  } catch (e) {
    toastError('甲方信息保存失败：' + (e && e.message ? e.message : e))
  }
}

async function loadContractStatus() {
  statusError.value = ''
  try {
    contractStatus.value = await fetchContractStatus()
  } catch (e) {
    contractStatus.value = null
    statusError.value = '合同数据状态读取失败：' + (e && e.message ? e.message : e)
  }
}

function pollSync() {
  clearTimeout(syncTimer)
  syncTimer = setTimeout(async () => {
    try {
      const data = await fetchSyncStatus()
      if (data.state === 'running') {
        syncMessage.value = data.message || '正在解析合同…'
        pollSync()
        return
      }
      if (data.state === 'done') {
        syncMessage.value = '更新完成，正在刷新…'
        await Promise.all([
          loadMeta(true),
          loadExpiry(true),
          loadContractStatus(),
          refreshSupplier(),
        ])
        syncing.value = false
        toastSuccess('合同数据已更新')
        return
      }
      syncing.value = false
      if (data.state === 'error') syncMessage.value = data.message || '更新失败'
    } catch (e) {
      syncing.value = false
      syncMessage.value = '读取更新进度失败：' + (e && e.message ? e.message : e)
    }
  }, 1500)
}

async function startSync() {
  if (syncing.value) return
  syncing.value = true
  syncMessage.value = '正在启动…'
  try {
    const data = await runSync()
    syncMessage.value = `正在处理 ${data.total || 0} 份合同，解析需要一点时间…`
    pollSync()
  } catch (e) {
    syncing.value = false
    syncMessage.value = e && e.message ? e.message : String(e)
  }
}

function goExpiry() {
  router.push('/expiry')
}

onMounted(() => {
  restoreSupplier()
  refreshSupplier()
  loadMeta().catch(() => {})
  loadPartyList()
  loadExpiry().catch(() => {})
  loadContractStatus()
})

onBeforeUnmount(() => {
  clearTimeout(syncTimer)
  clearTimeout(resetTimer)
})
</script>

<template>
  <div class="page">
    <div v-if="showExpiryBar" class="expiry-bar" :class="{ urgent: expiryUrgent }">
      <div class="eb-main">
        <span>合同到期：</span>
        <span>已过期 <b>{{ expiryCounts.expired || 0 }}</b> 家</span>
        <span>·</span>
        <span><b>{{ expiryCounts.d3 || 0 }}</b> 家 3 天内到期</span>
        <span>·</span>
        <span><b>{{ expiryCounts.d7 || 0 }}</b> 家 1 周内到期</span>
        <span>·</span>
        <span><b>{{ expiryCounts.d30 || 0 }}</b> 家 1 个月内到期</span>
        <span>·</span>
        <span><b>{{ expiryCounts.d90 || 0 }}</b> 家 3 个月内到期</span>
        <span class="muted">（共 {{ expirySupplierCount }} 家供应商，数据截至 {{ expiryDate }}）</span>
      </div>
      <button type="button" class="eb-btn" @click="goExpiry">查看并处理</button>
    </div>

    <section class="card">
      <div class="card-title"><span class="step">1</span>选择供应商</div>
      <div class="supplier-row">
        <div class="field supplier-search">
          <SearchSelect
            :key="supplierKeyVersion"
            label="输入供应商名称（支持模糊搜索）"
            placeholder="如：广东弘印包装科技有限公司"
            :model-value="supplier"
            :search="searchSuppliers"
            :option-title="supplierTitle"
            :option-detail="supplierDetail"
            :item-key="supplierKey"
            @update:model-value="onSupplierChange"
            @clear="removeSupplier"
            @edit="onSupplierEdit"
          />
          <div class="hint">输入关键字后从下拉列表选择；选择后会自动带出历史合同情况。</div>
        </div>
        <div v-if="supplier" class="field supplier-picked">
          <span class="field-label">已选供应商</span>
          <div class="picked-box">
            <div>
              <b>{{ supplier.name }}</b>
              <span class="tag">产品 {{ (supplier.product_ids || []).length }} 个</span>
            </div>
            <div v-if="supplier.phone" class="hint">电话 {{ supplier.phone }}</div>
          </div>
        </div>
      </div>

      <div v-if="supplier" class="contract-box" :class="boxTone">
        <template v-if="knownParties.length">
          <div class="cb-title">
            ✓ 已有主合同
            <span class="cb-sub" title="按合同台账统计，同一合同的多份副本不重复计数">
              共 {{ contractTotal }} 份历史合同
            </span>
          </div>
          <div class="cb-line">
            最近签约：<b>{{ latestParty ? cnDate(latestParty.latest_sign) : '—' }}</b>
            <span v-if="latestParty && latestParty.contract_no"> · {{ latestParty.contract_no }}</span>
          </div>
          <div v-for="row in sortedParties" :key="row.party_a_label" class="cb-party">
            <div class="cb-line">
              甲方：<b>{{ row.party_a_label }}</b> · {{ row.contract_count || 0 }} 份 ·
              最近 {{ row.latest_sign ? cnDate(row.latest_sign) : '无签约日期' }}
              <span v-if="row.contract_no">（{{ row.contract_no }}）</span>
            </div>
            <div class="cb-sub">
              期限 {{ row.start_date ? cnDate(row.start_date) + ' 至 ' : '至 ' }}{{ row.end_date ? cnDate(row.end_date) : '未登记到期日' }}
              <span v-if="row.end_date" class="cb-tag" :style="tagStyle(row)">{{ tagText(row) }}</span>
            </div>
          </div>
          <div class="cb-line">
            合同有效期：
            <template v-if="overallValidity">
              {{ overallValidity.start_date ? cnDate(overallValidity.start_date) + ' 至 ' : '至 ' }}
              <b>{{ cnDate(overallValidity.end_date) }}</b>
              <span class="cb-tag" :style="tagStyle(overallValidity)">{{ tagText(overallValidity) }}</span>
            </template>
            <template v-else>
              <span style="color:#8a5a00">未登记到期日</span>
              <a href="javascript:;" class="cb-link" @click="goExpiry">去登记</a>
            </template>
          </div>
          <div v-if="unconfirmedCount" class="cb-sub">
            另有 {{ unconfirmedCount }} 份合同未确认甲方，可到合同倒计时页核对。
          </div>
          <div class="hint">
            日期取自合同正文“已于…签订《购销框架合同》”一句。本次下单只需出《产品订购清单》，
            清单内自动引用该日期，无需重复签约主体合同。
          </div>
        </template>
        <template v-else-if="contractTotal">
          <div class="cb-title">有 {{ contractTotal }} 份历史合同，但未识别到主合同日期</div>
          <div class="hint">《产品订购清单》的主合同日期会留空，建议确认后再下单。</div>
        </template>
        <template v-else>
          <div class="cb-title">该供应商走月结模式（无框架合同）</div>
          <div class="hint">
            此类按月度对账结算，无需签订主合同。本次仍可正常下单，
            《产品订购清单》中的主合同日期留空即可。
          </div>
        </template>

        <div v-if="statusError" class="cb-meta">
          <div class="warn">{{ statusError }}</div>
        </div>
        <div v-if="freshnessVisible" class="cb-meta">
          <div v-if="freshness.data_updated_at">
            数据更新于 <b>{{ String(freshness.data_updated_at).slice(0, 16) }}</b>
            · 合同台账 {{ freshness.contract_records || 0 }} 份
          </div>
          <template v-if="pendingInfo.pending_count">
            <div class="warn">
              ⚠ 发现 {{ pendingInfo.pending_count }} 份新合同还没导入
              <span v-if="pendingInfo.newest_date">（最新 {{ String(pendingInfo.newest_date).slice(0, 10) }}）</span>
            </div>
            <div class="cb-actions">
              <button type="button" class="cb-btn" :disabled="syncing" @click="startSync">
                {{ syncing ? '正在更新…' : '立即更新' }}
              </button>
              <span class="cb-msg">{{ syncMessage || '解析后直接写入数据库，完成会自动刷新' }}</span>
            </div>
          </template>
          <div v-else-if="(pendingInfo.missing_dirs || []).length" class="muted">
            合同来源目录未连接，暂时无法核对是否有更新的合同。
          </div>
          <div v-else-if="pendingInfo.checked_at" class="ok">
            已核对合同来源目录，没有未导入的新合同。
          </div>
        </div>
      </div>
    </section>

    <section v-if="supplier || items.length" class="card">
      <div class="card-title">
        <span class="step">2</span>选择产品
        <span class="muted title-note">已选 {{ items.length }} 个产品</span>
        <button
          v-if="supplier"
          type="button"
          class="btn btn-ghost btn-sm title-action"
          @click="removeSupplier"
        >
          取消选择供应商
        </button>
      </div>
      <div class="field">
        <ProductSearch
          :key="productSearchKey"
          :supplier-id="supplier ? supplier.id : ''"
          :supplier-product-ids="supplier ? supplier.product_ids || [] : []"
          @pick="addProduct"
        />
        <div class="hint">
          优先显示该供应商的产品；产品<strong>别名</strong>和<strong>规格</strong>关键字也能搜到，如「U盘」「帆布袋」。
        </div>
      </div>

      <OrderTable
        v-if="items.length"
        class="stack-top"
        :items="items"
        @update="updateItem"
        @remove="removeItem"
        @cycle="cycleImage"
        @preview="previewImage = $event"
      />
      <div v-else class="empty-text">还没有添加产品，在上面的搜索框里搜索并点选即可。</div>
    </section>

    <section v-if="items.length" class="card">
      <div class="card-title"><span class="step">3</span>付款方式</div>
      <PayModePicker
        v-model="payMode"
        :total-cents="totalCents"
        :threshold="threshold"
        @update:threshold="setThreshold"
      />
    </section>

    <section v-if="items.length" class="card">
      <div class="total-bar">
        <div class="total-label">本次订购总金额（含税）</div>
        <div class="total-value"><small>¥ </small>{{ formatCents(totalCents) }}</div>
      </div>
      <div class="hint">
        已选 {{ items.length }} 个产品
        <span v-if="partyA"> · {{ partyA.name }}</span>
        <span v-if="payMode"> · {{ payModeLabel(payMode) }}</span>
        <span v-if="threshold !== null"> · 预付款起订金额 {{ formatMoney0(threshold) }} 元</span>
      </div>

      <div v-if="partyA" class="pa-block">
        <div class="pa-head">
          <span class="pa-title">甲方（我方）</span>
          <span class="hint">已预填默认信息，改动会自动记住；导出的清单和主体合同会带上公司名称与地址</span>
        </div>
        <div class="pa-grid">
          <label class="pa-field">
            <span>公司名称</span>
            <select v-model="partyA" @change="onPartyAChange">
              <option v-for="item in partyAList" :key="item.name" :value="item">
                {{ item.name }}
              </option>
            </select>
          </label>
          <label class="pa-field">
            <span>统一社会信用代码</span>
            <input :value="partyA.credit_code" readonly />
          </label>
          <label class="pa-field">
            <span>联系人</span>
            <input v-model="partyA.contact" @change="savePartyInfo" />
          </label>
          <label class="pa-field">
            <span>联系电话</span>
            <input v-model="partyA.tel" @change="savePartyInfo" />
          </label>
          <label class="pa-field">
            <span>联系邮箱</span>
            <input v-model="partyA.email" @change="savePartyInfo" />
          </label>
          <label class="pa-field pa-full">
            <span>联系地址</span>
            <input v-model="partyA.addr" @change="savePartyInfo" />
          </label>
        </div>
        <div class="hint">{{ partyAHint }}</div>
      </div>

      <div class="actions">
        <button type="button" class="btn btn-ghost" @click="resetAll">
          {{ resetArmed ? '再点一次确认清空' : '清空重来' }}
        </button>
        <button type="button" class="btn btn-ghost" @click="exportMainContract">
          导出主体合同（需签时用）
        </button>
        <button type="button" class="btn btn-primary" :disabled="exporting" @click="exportOrder">
          {{ exporting ? exportHint || '正在生成…' : '导出订购清单（日常下单）' }}
        </button>
      </div>
    </section>

    <div v-if="previewImage" class="modal-mask" @click.self="previewImage = ''">
      <div class="image-modal">
        <button type="button" class="modal-close" @click="previewImage = ''">×</button>
        <img :src="previewImage" alt="产品图片" />
      </div>
    </div>
  </div>
</template>
