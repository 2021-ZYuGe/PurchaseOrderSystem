<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import SearchSelect from '../components/SearchSelect.vue'
import PayModePicker from '../components/PayModePicker.vue'
import { fetchArchive, saveArchive } from '../api/catalog'
import { generateContract, generateInfoSheet } from '../api/contracts'
import { usePayThreshold } from '../composables/usePayThreshold'
import { useToast } from '../composables/useToast'
import { inputToCents, resolveOutputUrl, todayISO } from '../lib/format'

const PARTY_A_CODES = {
  广州兴趣岛信息科技有限公司: '91440104MA59C33C5N',
  广州普惠优品电子商贸有限公司: '91440106MA7LKA4517',
}
const PARTY_A_NAMES = Object.keys(PARTY_A_CODES)
const DEFAULT_PARTY_A = {
  name: '广州兴趣岛信息科技有限公司',
  credit_code: '91440104MA59C33C5N',
  contact: '简丽冰',
  tel: '15814464431',
  email: '457263395@qq.com',
  addr: '广州市天河区奥体南路9号兴创楼二楼203供应链组',
}
const B_KEYS = [
  'name',
  'credit_code',
  'contact',
  'tel',
  'email',
  'wechat',
  'addr',
  'bank_name',
  'bank_account',
  'bank_open',
]

function loadPartyA() {
  const base = { ...DEFAULT_PARTY_A }
  try {
    const saved = JSON.parse(localStorage.getItem('partyA_v2') || '{}')
    Object.keys(base).forEach((key) => {
      if (String(saved[key] || '').trim()) base[key] = saved[key]
    })
  } catch (e) {
    /* 忽略 */
  }
  return base
}

const { threshold, setThreshold } = usePayThreshold()
const { success: toastSuccess } = useToast()
const route = useRoute()

const mode = ref('')
const type = ref('batch')
const archive = ref([])
const selectedArchive = ref(null)
const archiveLoading = ref(false)
const pickedInfo = ref('')
const generating = ref(false)
const infoGenerating = ref(false)
const savingArchive = ref(false)
const formError = ref('')
const contractResult = ref(null)
const infoResult = ref(null)

const form = reactive({
  party_a: loadPartyA(),
  party_b: {
    name: '',
    credit_code: '',
    contact: '',
    tel: '',
    email: '',
    wechat: '',
    addr: '',
    bank_name: '',
    bank_account: '',
    bank_open: '',
  },
  sign: { date: todayISO(), years: '1', place: '广州市天河区' },
  terms: {
    tax_rate: '13',
    invoice_type: '专票',
    invoice_days: '15',
    pay_days: '15',
    delivery_days: '10',
    reconcile_days: '2',
    invalid_order_pct: '5',
    delivery_addr: '',
    order_amount: '',
    pay_mode: 'full',
  },
})
if (PARTY_A_CODES[form.party_a.name]) form.party_a.credit_code = PARTY_A_CODES[form.party_a.name]

const isDropship = computed(() => type.value === 'dropship')
const isSimple = computed(() => type.value === 'simple')
const showYears = computed(() => !isSimple.value)
const showAmount = computed(() => !isDropship.value)
const showPayMode = computed(() => !isDropship.value)
const showDropshipTerms = computed(() => isDropship.value)

const stepType = computed(() => (mode.value === 'renew' ? 3 : 2))
const stepPartyB = computed(() => (mode.value === 'renew' ? 4 : 3))
const stepPartyA = computed(() => (mode.value === 'renew' ? 5 : 4))
const stepTerms = computed(() => (mode.value === 'renew' ? 6 : 5))

const amountCents = computed(() => inputToCents(form.terms.order_amount))

const REQUIRED = {
  batch: [
    ['party_b.name', '公司全称'],
    ['party_b.credit_code', '统一社会信用代码'],
    ['party_b.contact', '联系人'],
    ['party_b.tel', '联系电话'],
    ['party_b.email', '联系邮箱'],
    ['party_b.addr', '联系地址'],
    ['party_b.bank_name', '开户名称'],
    ['party_b.bank_account', '对公账号'],
    ['party_b.bank_open', '开户行'],
    ['sign.date', '签约日期'],
    ['sign.years', '合同期限（年）'],
    ['terms.order_amount', '本次订单总金额'],
  ],
  simple: [
    ['party_b.name', '公司全称'],
    ['party_b.contact', '联系人'],
    ['party_b.tel', '联系电话'],
    ['party_b.email', '联系邮箱'],
    ['party_b.addr', '联系地址'],
    ['party_b.bank_name', '开户名称'],
    ['party_b.bank_account', '开户账号'],
    ['party_b.bank_open', '开户行'],
    ['sign.date', '签约日期'],
    ['terms.order_amount', '本次订单总金额'],
  ],
  dropship: [
    ['party_b.name', '公司全称'],
    ['party_b.addr', '联系地址'],
    ['party_b.bank_account', '对公账号'],
    ['party_b.bank_open', '开户行'],
    ['sign.date', '签约日期'],
  ],
}

const REQ_HINT = {
  batch:
    '批采必填：公司全称、信用代码、联系人、电话、邮箱、地址、开户名称、对公账号、开户行、订单总金额、合同期限。',
  simple:
    '简易版必填：公司全称、联系人、电话、邮箱、地址、开户名称、开户账号、开户行、订单总金额。',
  dropship: '一件代发必填：公司全称、联系地址、对公账号、开户行、签约日期。',
}

function getValue(path) {
  return String(
    path.split('.').reduce((target, key) => (target ? target[key] : ''), form) ?? '',
  ).trim()
}

async function loadArchive() {
  archiveLoading.value = true
  try {
    const data = await fetchArchive()
    archive.value = data.profiles || []
    const profile = data.party_a && data.party_a[form.party_a.name]
    if (profile) {
      ;['name', 'credit_code', 'contact', 'tel', 'email', 'addr'].forEach((key) => {
        if (!String(form.party_a[key] || '').trim() && profile[key]) form.party_a[key] = profile[key]
      })
    }
  } catch (e) {
    formError.value = '供应商档案读取失败：' + (e && e.message ? e.message : e)
  } finally {
    archiveLoading.value = false
  }
}

function searchArchive(q) {
  const text = String(q || '').trim().toLowerCase()
  if (!text) return archive.value.slice(0, 12)
  return archive.value
    .filter((item) => String(item.name || '').toLowerCase().includes(text))
    .slice(0, 12)
}

function archiveTitle(item) {
  return item.name
}

function archiveDetail(item) {
  const parts = []
  if (item.contact) parts.push('联系人 ' + item.contact)
  if (item.tel) parts.push('电话 ' + item.tel)
  if (item.last_sign) parts.push('上次签约 ' + item.last_sign)
  if (item.source) parts.push('来源 ' + item.source)
  return parts.join(' · ')
}

function archiveKey(item) {
  return item.name
}

function fillPartyB(profile) {
  B_KEYS.forEach((key) => {
    form.party_b[key] = profile[key] || ''
  })
  if (!form.party_b.bank_name.trim()) form.party_b.bank_name = profile.name || ''
}

function clearPartyB() {
  B_KEYS.forEach((key) => {
    form.party_b[key] = ''
  })
  form.terms.order_amount = ''
}

function onArchivePick(profile) {
  if (!profile) {
    selectedArchive.value = null
    pickedInfo.value = ''
    return
  }
  selectedArchive.value = profile
  fillPartyB(profile)
  const parts = [`已带入 ${profile.name} 的历史信息`]
  if (profile.last_sign) parts.push('上次签约：' + profile.last_sign)
  parts.push('请重点核对账号、开户行、税率、金额和这次的签约日期。')
  pickedInfo.value = parts.join('。')
}

function setMode(next) {
  mode.value = next
  pickedInfo.value = ''
  formError.value = ''
  if (next === 'new') {
    selectedArchive.value = null
    clearPartyB()
  }
}

function setType(next) {
  type.value = next
  if (next === 'dropship') form.terms.pay_mode = 'full'
}

function validate() {
  const missing = []
  ;(REQUIRED[type.value] || []).forEach(([path, label]) => {
    if (!getValue(path)) missing.push(label)
  })
  if (missing.length) {
    formError.value = '以下必填项还没填：' + missing.join('、')
    return false
  }
  if (!isDropship.value) {
    const raw = String(form.terms.order_amount || '').replace(/,/g, '').trim()
    if (!/^\d+(\.\d{1,2})?$/.test(raw) || parseFloat(raw) <= 0) {
      formError.value = '本次订单总金额请填数字，例如 12500 或 12500.50。'
      return false
    }
  }
  if (type.value === 'batch' && !/^[1-9]\d*$/.test(String(form.sign.years || '').trim())) {
    formError.value = '合同期限请填正整数年数，例如 1。'
    return false
  }
  const numeric = [['terms.delivery_days', '交货周期']]
  if (isDropship.value) {
    numeric.push(['terms.invoice_days', '开票期限'], ['terms.pay_days', '付款期限'])
  }
  for (const [path, label] of numeric) {
    if (!/^\d+$/.test(getValue(path))) {
      formError.value = label + '请填数字。'
      return false
    }
  }
  return true
}

function payload() {
  return {
    contract_type: type.value,
    remember: mode.value === 'new',
    party_a: { ...form.party_a },
    party_b: { ...form.party_b },
    sign: { ...form.sign },
    terms: {
      ...form.terms,
      order_amount: String(form.terms.order_amount || '').replace(/,/g, '').trim(),
    },
  }
}

async function generate() {
  if (generating.value) return
  formError.value = ''
  if (!mode.value) {
    formError.value = '先在第 1 步选择：这次是「续签 / 到期重签」还是「首次签约」。'
    return
  }
  if (!form.party_b.bank_name.trim() && form.party_b.name.trim()) {
    form.party_b.bank_name = form.party_b.name.trim()
  }
  if (!validate()) return
  generating.value = true
  contractResult.value = null
  try {
    const data = await generateContract(payload())
    contractResult.value = { ...data, url: resolveOutputUrl(data.url) }
    toastSuccess('合同已生成，可下载查看')
    if (mode.value === 'new') loadArchive().catch(() => {})
  } catch (e) {
    formError.value = '生成失败：' + (e && e.message ? e.message : e)
  } finally {
    generating.value = false
  }
}

async function exportInfo() {
  if (infoGenerating.value) return
  formError.value = ''
  if (!form.party_b.name.trim()) {
    formError.value = '先填一下乙方公司名，信息收集表上会带上名字。'
    return
  }
  infoGenerating.value = true
  infoResult.value = null
  try {
    const data = await generateInfoSheet({ ...form.party_b })
    infoResult.value = { ...data, url: resolveOutputUrl(data.url) }
    toastSuccess('信息收集表已生成')
  } catch (e) {
    formError.value = '生成信息收集表失败：' + (e && e.message ? e.message : e)
  } finally {
    infoGenerating.value = false
  }
}

async function saveOnly() {
  if (savingArchive.value) return
  formError.value = ''
  if (!form.party_b.name.trim()) {
    formError.value = '公司名不能为空。'
    return
  }
  savingArchive.value = true
  try {
    await saveArchive({
      name: form.party_b.name.trim(),
      credit_code: form.party_b.credit_code.trim(),
      contact: form.party_b.contact.trim(),
      tel: form.party_b.tel.trim(),
      email: form.party_b.email.trim(),
      wechat: form.party_b.wechat.trim(),
      addr: form.party_b.addr.trim(),
      legal: '',
      bank_name: form.party_b.bank_name.trim() || form.party_b.name.trim(),
      bank_account: form.party_b.bank_account.trim(),
      bank_open: form.party_b.bank_open.trim(),
      last_sign: form.sign.date || '',
      source: '合同',
    })
    toastSuccess('已存入供应商档案')
    await loadArchive()
    const hit = archive.value.find((item) => item.name === form.party_b.name.trim())
    if (hit) selectedArchive.value = hit
  } catch (e) {
    formError.value = '保存档案失败：' + (e && e.message ? e.message : e)
  } finally {
    savingArchive.value = false
  }
}

watch(
  () => form.party_a.name,
  (name) => {
    if (PARTY_A_CODES[name]) form.party_a.credit_code = PARTY_A_CODES[name]
  },
)

watch(
  () => form.party_b.name,
  (name) => {
    if (!form.party_b.bank_name.trim()) form.party_b.bank_name = String(name || '').trim()
  },
)

watch(
  () => form.party_a,
  (value) => {
    try {
      localStorage.setItem('partyA_v2', JSON.stringify(value))
    } catch (e) {
      /* 忽略 */
    }
  },
  { deep: true },
)

async function applyRenewQuery() {
  mode.value = 'renew'
  const name = String(route.query.supplier || '').trim()
  await loadArchive()
  if (!name) return
  const hit = archive.value.find((profile) => profile.name === name)
  if (hit) {
    selectedArchive.value = hit
    onArchivePick(hit)
  } else {
    selectedArchive.value = { name }
    clearPartyB()
    form.party_b.name = name
    pickedInfo.value = '档案里没有 ' + name + ' 的完整信息，已填公司名，其余请手工补充。'
  }
}

onMounted(async () => {
  if (String(route.query.mode || '') === 'renew') {
    await applyRenewQuery()
  } else {
    await loadArchive()
  }
})
</script>

<template>
  <div class="page page-narrow">
    <div class="page-heading">
      <h1>新增主合同</h1>
      <p class="muted">新签 / 续签 · 生成 Word 主合同或供应商信息收集表</p>
    </div>

    <section class="card">
      <div class="card-title"><span class="step">1</span>这次是哪种情况</div>
      <div class="mode-grid">
        <button
          type="button"
          class="mode-opt"
          :class="{ active: mode === 'renew' }"
          @click="setMode('renew')"
        >
          <span class="mt">续签 / 到期重签 <span class="tag tag-green">老供应商</span></span>
          <span class="md">
            以前签过（档案里能搜到）→ 联系人、地址、电话、邮箱、公户信息自动带回，你只改日期。
          </span>
        </button>
        <button
          type="button"
          class="mode-opt"
          :class="{ active: mode === 'new' }"
          @click="setMode('new')"
        >
          <span class="mt">首次签约 <span class="tag tag-danger">新供应商</span></span>
          <span class="md">
            第一次合作 → 把对方信息填一遍；生成后自动存进档案，下次续签直接搜名字就能带出来。
          </span>
        </button>
      </div>
      <div v-if="!mode" class="hint">先选上面的一项，再继续填写。</div>
    </section>

    <section v-if="mode === 'renew'" class="card">
      <div class="card-title"><span class="step">2</span>选供应商</div>
      <div class="field">
        <SearchSelect
          label="输入公司名搜索（支持模糊匹配）"
          placeholder="如：深圳骐思创新电子科技有限公司"
          :model-value="selectedArchive"
          :search="searchArchive"
          :option-title="archiveTitle"
          :option-detail="archiveDetail"
          :item-key="archiveKey"
          @update:model-value="onArchivePick"
        />
        <div class="hint">
          档案里共 <b>{{ archive.length }}</b> 家历史供应商
          <span v-if="archiveLoading">（读取中…）</span>。搜不到说明以前没签过，切到「首次签约」手填即可。
        </div>
      </div>
      <div v-if="pickedInfo" class="notice notice-ok stack-top">
        <div>{{ pickedInfo }}</div>
      </div>
    </section>

    <section class="card">
      <div class="card-title"><span class="step">{{ stepType }}</span>合同类型</div>
      <div class="mode-grid">
        <button
          type="button"
          class="mode-opt"
          :class="{ active: type === 'batch' }"
          @click="setType('batch')"
        >
          <span class="mt">一次性发货（批采）</span>
          <span class="md">货一次性发到我方仓库，适用于大批量采购；使用集采模式合同模板。</span>
        </button>
        <button
          type="button"
          class="mode-opt"
          :class="{ active: type === 'dropship' }"
          @click="setType('dropship')"
        >
          <span class="mt">一件代发</span>
          <span class="md">供应商按单直发给客户，按月结算。</span>
        </button>
        <button
          type="button"
          class="mode-opt"
          :class="{ active: type === 'simple' }"
          @click="setType('simple')"
        >
          <span class="mt">单次简易版</span>
          <span class="md">单次采购、一次结清，使用《产品订购协议》简易模板。</span>
        </button>
      </div>
      <div class="hint req-hint">{{ REQ_HINT[type] }}</div>
    </section>

    <section class="card">
      <div class="card-title"><span class="step">{{ stepPartyB }}</span>乙方（供应商）信息</div>
      <div class="form-grid">
        <div class="field full">
          <label class="field-label">公司全称 <span class="req">*</span></label>
          <input v-model="form.party_b.name" placeholder="须与营业执照一致" />
        </div>
        <div v-if="type !== 'simple' && !isDropship" class="field">
          <label class="field-label">统一社会信用代码 <span class="req">*</span></label>
          <input v-model="form.party_b.credit_code" />
        </div>
        <div v-if="!isDropship" class="field">
          <label class="field-label">联系人 <span class="req">*</span></label>
          <input v-model="form.party_b.contact" />
        </div>
        <div v-if="!isDropship" class="field">
          <label class="field-label">联系电话 <span class="req">*</span></label>
          <input v-model="form.party_b.tel" />
        </div>
        <div v-if="!isDropship" class="field">
          <label class="field-label">联系邮箱 <span class="req">*</span></label>
          <input v-model="form.party_b.email" />
        </div>
        <div class="field">
          <label class="field-label">微信号</label>
          <input v-model="form.party_b.wechat" />
        </div>
        <div class="field full">
          <label class="field-label">联系地址 <span class="req">*</span></label>
          <input v-model="form.party_b.addr" placeholder="须能收寄快递" />
        </div>

        <div class="section-title full">收款账户（必须对公）</div>
        <div class="field full">
          <label class="field-label">开户名称 <span v-if="!isDropship" class="req">*</span></label>
          <input v-model="form.party_b.bank_name" placeholder="一般就是公司全称" />
        </div>
        <div class="field">
          <label class="field-label">
            {{ type === 'simple' ? '开户账号' : '对公账号' }} <span class="req">*</span>
          </label>
          <input v-model="form.party_b.bank_account" />
        </div>
        <div class="field">
          <label class="field-label">开户行 <span class="req">*</span></label>
          <input v-model="form.party_b.bank_open" placeholder="精确到支行" />
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-title">
        <span class="step">{{ stepPartyA }}</span>甲方（我方）信息
        <span class="muted title-note">已预填默认信息，改动会自动记住</span>
      </div>
      <div class="form-grid">
        <div class="field full">
          <label class="field-label">公司名称</label>
          <select v-model="form.party_a.name">
            <option v-for="name in PARTY_A_NAMES" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div class="field">
          <label class="field-label">统一社会信用代码</label>
          <input v-model="form.party_a.credit_code" readonly title="随公司名称自动带出" />
        </div>
        <div class="field">
          <label class="field-label">联系人</label>
          <input v-model="form.party_a.contact" />
        </div>
        <div class="field">
          <label class="field-label">联系电话</label>
          <input v-model="form.party_a.tel" />
        </div>
        <div class="field">
          <label class="field-label">联系邮箱</label>
          <input v-model="form.party_a.email" />
        </div>
        <div class="field full">
          <label class="field-label">联系地址</label>
          <input v-model="form.party_a.addr" />
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-title"><span class="step">{{ stepTerms }}</span>签约与商务条款</div>
      <div class="form-grid">
        <div class="field">
          <label class="field-label">签约日期 <span class="req">*</span></label>
          <input v-model="form.sign.date" type="date" />
        </div>
        <div v-if="showYears" class="field">
          <label class="field-label">
            合同期限（年）<span v-if="type === 'batch'" class="req">*</span>
          </label>
          <input v-model="form.sign.years" />
        </div>
        <div class="field">
          <label class="field-label">签署地</label>
          <input v-model="form.sign.place" />
        </div>
        <div v-if="showAmount" class="field">
          <label class="field-label">本次订单总金额（元） <span class="req">*</span></label>
          <input v-model="form.terms.order_amount" placeholder="如：12500 或 12500.50" />
          <div class="hint">批采取附件 2，简易版同时生成大写；代发不用填。</div>
        </div>

        <div v-if="showPayMode" class="field full">
          <PayModePicker
            v-model="form.terms.pay_mode"
            :total-cents="amountCents"
            :threshold="threshold"
            @update:threshold="setThreshold"
          />
        </div>

        <div class="section-title full">以下已按习惯预填，可临时修改</div>
        <div class="field">
          <label class="field-label">开票税率</label>
          <input v-model="form.terms.tax_rate" placeholder="13" />
        </div>
        <div class="field">
          <label class="field-label">发票类型</label>
          <select v-model="form.terms.invoice_type">
            <option value="专票">增值税专用发票</option>
            <option value="普票">增值税普通发票</option>
          </select>
        </div>
        <div v-if="showDropshipTerms" class="field">
          <label class="field-label">开票期限（工作日）</label>
          <input v-model="form.terms.invoice_days" />
        </div>
        <div v-if="showDropshipTerms" class="field">
          <label class="field-label">付款期限（工作日）</label>
          <input v-model="form.terms.pay_days" />
        </div>
        <div class="field">
          <label class="field-label">交货周期（自然日）</label>
          <input v-model="form.terms.delivery_days" />
        </div>
        <div v-if="showDropshipTerms" class="field">
          <label class="field-label">对账确认（工作日）</label>
          <input v-model="form.terms.reconcile_days" />
        </div>
        <div v-if="showDropshipTerms" class="field">
          <label class="field-label">无效发货占比上限（%）</label>
          <input v-model="form.terms.invalid_order_pct" />
          <div class="hint">超过该比例甲方可无条件解约。</div>
        </div>
        <div class="field full">
          <label class="field-label">交货地址（附件 2 用）</label>
          <input v-model="form.terms.delivery_addr" placeholder="留空则保持模板原样" />
        </div>
      </div>
    </section>

    <section class="card">
      <div v-if="formError" class="notice notice-error">{{ formError }}</div>

      <div v-if="contractResult" class="notice notice-ok stack-top">
        <div>
          已生成 <b>{{ contractResult.name }}</b>
        </div>
        <ul v-if="(contractResult.todo || []).length" class="plain-list">
          <li v-for="(todo, index) in contractResult.todo" :key="index">
            待手工确认：{{ todo }}
          </li>
        </ul>
        <div class="actions-inline">
          <a
            class="btn btn-primary btn-sm"
            :href="contractResult.url"
            target="_blank"
            rel="noopener"
            download
          >
            下载合同 Word
          </a>
        </div>
      </div>

      <div v-if="infoResult" class="notice notice-ok stack-top">
        <div>信息收集表 <b>{{ infoResult.name }}</b> 已生成，可直接发给对方填写。</div>
        <div class="actions-inline">
          <a
            class="btn btn-primary btn-sm"
            :href="infoResult.url"
            target="_blank"
            rel="noopener"
            download
          >
            下载信息收集表
          </a>
        </div>
      </div>

      <div class="actions">
        <button type="button" class="btn btn-ghost" :disabled="infoGenerating" @click="exportInfo">
          {{ infoGenerating ? '生成中…' : '导出信息收集表（发给对方填）' }}
        </button>
        <button type="button" class="btn btn-ghost" :disabled="savingArchive" @click="saveOnly">
          {{ savingArchive ? '保存中…' : '仅存入档案' }}
        </button>
        <button type="button" class="btn btn-primary" :disabled="generating" @click="generate">
          {{ generating ? '生成中…' : '生成合同 Word' }}
        </button>
      </div>
      <div class="hint" style="text-align: right">
        生成后请务必打开核对：公司名、账号、开户行、税率、金额、日期。
      </div>
    </section>
  </div>
</template>
