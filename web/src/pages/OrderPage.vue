<script setup>
import { computed, onMounted, ref } from 'vue'
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
import { amountCents, cnDate, daysLeft, formatCents, formatMoney0 } from '../lib/format'

const { findSuppliers, loadMeta } = useCatalog()
const { threshold, setThreshold } = usePayThreshold()
const { load: loadExpiry, findExpiry } = useExpiry()
const { notify, error: toastError, success: toastSuccess } = useToast()

const supplier = ref(null)
const items = ref([])
const payMode = ref('full')
const exporting = ref(false)
const exportHint = ref('')
const previewImage = ref('')
const resetArmed = ref(false)

let resetTimer = null

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

function onSupplierChange(value) {
  supplier.value = value || null
  if (!value) {
    try {
      sessionStorage.removeItem('lastSupplier')
    } catch (e) {
      /* 忽略 */
    }
    return
  }
  try {
    sessionStorage.setItem('lastSupplier', JSON.stringify(value))
  } catch (e) {
    /* 忽略 */
  }
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
}

function removeItem(id) {
  items.value = items.value.filter((it) => it.id !== id)
}

function cycleImage(id) {
  const item = items.value.find((it) => it.id === id)
  if (!item || item.images.length < 2) return
  const index = item.images.indexOf(item.image)
  item.image = item.images[(index + 1) % item.images.length]
}

const totalCents = computed(() =>
  items.value.reduce((sum, item) => sum + amountCents(item.unitPrice, item.qty), 0),
)

const supplierExpiry = computed(() => (supplier.value ? findExpiry(supplier.value.name) : null))

const supplierContract = computed(() => {
  const s = supplier.value
  if (!s) return null
  const ex = supplierExpiry.value
  const count = s.contract_count || 0
  const main = s.main_contract_date || ''
  let kind = 'monthly'
  if (main) kind = 'main'
  else if (count) kind = 'historical'
  return {
    kind,
    count,
    main,
    latest: s.latest_sign_date || main,
    latestNo: s.latest_contract_no || '',
    expiry: ex,
    days: ex && ex.end_date ? daysLeft(ex.end_date) : null,
  }
})

const contractTone = computed(() => {
  const info = supplierContract.value
  if (!info) return 'notice-info'
  if (info.days !== null && info.days <= 7) return 'notice-error'
  if (info.kind === 'main') return 'notice-ok'
  if (info.kind === 'historical') return 'notice-warn'
  return 'notice-info'
})

function daysText(days) {
  if (days === null || days === undefined) return ''
  if (days < 0) return `已过期 ${-days} 天`
  if (days === 0) return '今天到期'
  return `剩 ${days} 天`
}

function removeSupplier() {
  supplier.value = null
  try {
    sessionStorage.removeItem('lastSupplier')
  } catch (e) {
    /* 忽略 */
  }
}

async function exportOrder() {
  if (exporting.value) return
  if (!supplier.value) {
    toastError('请先选择供应商')
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
  exporting.value = true
  exportHint.value = '正在打包图片…'
  try {
    const result = await buildOrderDocx({
      supplier: supplier.value,
      items: items.value,
      payMode: payMode.value,
      totalCents: totalCents.value,
    })
    exportHint.value = '正在生成 Word…'
    downloadDocx(result.blob, result.filename)
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
  try {
    const result = buildMainContractDocx(supplier.value, threshold.value)
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
  items.value = []
  payMode.value = 'full'
  removeSupplier()
  toastSuccess('已清空当前订单')
}

onMounted(() => {
  restoreSupplier()
  loadMeta().catch(() => {})
  loadExpiry().catch(() => {})
})
</script>

<template>
  <div class="page">
    <section class="card">
      <div class="card-title"><span class="step">1</span>选择供应商</div>
      <div class="form-grid">
        <div class="field">
          <SearchSelect
            label="输入供应商名称（支持模糊搜索）"
            placeholder="如：广东弘印包装科技有限公司"
            :model-value="supplier"
            :search="searchSuppliers"
            :option-title="supplierTitle"
            :option-detail="supplierDetail"
            :item-key="supplierKey"
            @update:model-value="onSupplierChange"
          />
          <div class="hint">输入关键字后从下拉列表选择；选择后会自动带出历史合同情况。</div>
        </div>
        <div v-if="supplier" class="field">
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

      <div v-if="supplierContract" class="notice stack-top" :class="contractTone">
        <template v-if="supplierContract.kind === 'main'">
          <div>
            ✓ 已有主合同
            <span class="muted">共 {{ supplierContract.count }} 份历史合同</span>
          </div>
          <div class="notice-line">
            最近签约：<b>{{ cnDate(supplierContract.latest) }}</b>
            <span v-if="supplierContract.latestNo"> · {{ supplierContract.latestNo }}</span>
          </div>
          <div v-if="supplierContract.expiry && supplierContract.expiry.end_date" class="notice-line">
            合同有效期：{{ supplierContract.expiry.start_date ? cnDate(supplierContract.expiry.start_date) + ' 至 ' : '至 ' }}
            <b>{{ cnDate(supplierContract.expiry.end_date) }}</b>
            <span class="tag" :class="supplierContract.days <= 7 ? 'tag-danger' : 'tag-plain'">
              {{ daysText(supplierContract.days) }}
            </span>
            <span v-if="supplierContract.expiry.pending" class="tag tag-plain">需核对</span>
          </div>
          <div v-else class="hint">合同期限：未登记到期日，可到「合同倒计时」页登记。</div>
          <div class="hint">
            本次下单只需出《产品订购清单》，清单会自动引用最近的签约日期，无需重复签主体合同。
          </div>
        </template>

        <template v-else-if="supplierContract.kind === 'historical'">
          <div>有 {{ supplierContract.count }} 份历史合同，但未识别到主合同日期</div>
          <div class="hint">《产品订购清单》的主合同日期会留空，建议确认后再下单。</div>
        </template>

        <template v-else>
          <div>该供应商走月结模式（无框架合同）</div>
          <div class="hint">此类按月度对账结算，无需签订主合同，本次仍可正常下单。</div>
        </template>
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
        <span v-if="payMode"> · {{ payModeLabel(payMode) }}</span>
        <span v-if="threshold !== null"> · 预付款起订金额 {{ formatMoney0(threshold) }} 元</span>
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
