<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { removeTerm, saveTerm } from '../api/contracts'
import { useExpiry } from '../composables/useExpiry'
import { useToast } from '../composables/useToast'
import { cnDate, daysLeft } from '../lib/format'

const router = useRouter()
const { expiry, loading, error, load } = useExpiry()
const { success: toastSuccess } = useToast()

const filter = ref('all')
const termOpen = ref(false)
const termItem = ref(null)
const termError = ref('')
const termSaving = ref(false)
const termForm = reactive({ supplier: '', start_date: '', end_date: '', note: '' })

const counts = computed(() => (expiry.value && expiry.value.counts) || {})
const soon7 = computed(() => (counts.value.d3 || 0) + (counts.value.d7 || 0))
const soon30 = computed(() => soon7.value + (counts.value.d30 || 0))
const unknown = computed(() => (counts.value.pending || 0) + (counts.value.unknown || 0))
const urgentCount = computed(() => (counts.value.expired || 0) + soon30.value)

const buckets = computed(() => (expiry.value && expiry.value.buckets) || [])
const visibleBuckets = computed(() => buckets.value.filter((item) => item.count > 0))

function sortKey(item) {
  const left = item.days_left
  if (left === null || left === undefined) return 1e9
  // 已过期的按“刚过期”排前面，其余按剩余天数从少到多
  return left < 0 ? -100000 + Math.abs(left) : left
}

const filteredItems = computed(() => {
  let items = [...((expiry.value && expiry.value.items) || [])]
  if (filter.value === 'urgent') {
    items = items.filter((item) => ['expired', 'd3', 'd7', 'd30'].includes(item.bucket))
  } else if (filter.value !== 'all') {
    items = items.filter((item) => item.bucket === filter.value)
  }
  return items.sort((a, b) => sortKey(a) - sortKey(b))
})

const canDeleteTerm = computed(() => {
  const source = String((termItem.value && termItem.value.source) || '')
  return source === 'manual' || source.includes('手工')
})

function leftText(endDate) {
  const left = daysLeft(endDate)
  if (left === null) return '未登记'
  if (left < 0) return `已过期 ${-left} 天`
  if (left === 0) return '今天到期'
  return `剩 ${left} 天`
}

function leftClass(item) {
  const left = item.days_left
  if (left === null || left === undefined) return 'muted'
  if (left < 0 || left <= 7) return 'text-danger'
  if (left <= 30) return 'text-warn'
  return ''
}

function periodText(item) {
  if (item.start_date && item.end_date) {
    return `${cnDate(item.start_date)} 至 ${cnDate(item.end_date)}`
  }
  if (item.end_date) return `至 ${cnDate(item.end_date)}`
  return '—'
}

function renew(item) {
  router.push({ path: '/contract', query: { mode: 'renew', supplier: item.supplier } })
}

function openTerm(item) {
  termItem.value = item
  termForm.supplier = item.supplier
  termForm.start_date = item.start_date || ''
  termForm.end_date = item.end_date || ''
  termForm.note = item.note || ''
  termError.value = ''
  termOpen.value = true
}

function closeTerm() {
  termOpen.value = false
  termItem.value = null
}

async function submitTerm() {
  termError.value = ''
  if (!termForm.end_date) {
    termError.value = '请填写到期日期'
    return
  }
  if (termForm.start_date && termForm.end_date < termForm.start_date) {
    termError.value = '到期日期不能早于起始日期'
    return
  }
  termSaving.value = true
  try {
    const data = await saveTerm({ ...termForm })
    if (data.overview) expiry.value = data.overview
    closeTerm()
    toastSuccess('合同期限已保存')
  } catch (e) {
    termError.value = e && e.message ? e.message : String(e)
  } finally {
    termSaving.value = false
  }
}

async function deleteTermEntry() {
  if (!termItem.value) return
  termSaving.value = true
  termError.value = ''
  try {
    const data = await removeTerm(termForm.supplier)
    if (data.overview) expiry.value = data.overview
    closeTerm()
    toastSuccess('已撤销手工登记的期限')
  } catch (e) {
    termError.value = e && e.message ? e.message : String(e)
  } finally {
    termSaving.value = false
  }
}

onMounted(() => {
  load(true).catch(() => {})
})
</script>

<template>
  <div class="page">
    <div class="page-heading">
      <h1>合同倒计时</h1>
      <p class="muted">
        按剩余天数排序，已过期和 30 天内到期优先；点「续签」会带着供应商进入新增主合同页。
      </p>
    </div>

    <section class="card">
      <div class="card-title">
        到期概览
        <span v-if="expiry && expiry.today" class="muted title-note">数据截至 {{ expiry.today }}</span>
        <button
          type="button"
          class="btn btn-ghost btn-sm title-action"
          :disabled="loading"
          @click="load(true)"
        >
          {{ loading ? '读取中…' : '刷新' }}
        </button>
      </div>

      <div v-if="error && !expiry" class="notice notice-error">到期数据读取失败：{{ error }}</div>
      <div v-else-if="!expiry" class="empty-text">正在读取合同期限…</div>
      <template v-else>
        <div class="stat-grid">
          <div class="stat-card stat-danger">
            <b>{{ counts.expired || 0 }}</b>
            <span>已过期</span>
          </div>
          <div class="stat-card stat-warn">
            <b>{{ soon7 }}</b>
            <span>7 天内到期</span>
          </div>
          <div class="stat-card">
            <b>{{ soon30 }}</b>
            <span>30 天内到期</span>
          </div>
          <div class="stat-card">
            <b>{{ unknown }}</b>
            <span>未登记 / 待确认</span>
          </div>
        </div>

        <div class="bucket-row">
          <button
            type="button"
            class="bucket"
            :class="{ active: filter === 'all' }"
            @click="filter = 'all'"
          >
            全部 <b>{{ expiry.total }}</b>
          </button>
          <button
            type="button"
            class="bucket"
            :class="{ active: filter === 'urgent' }"
            @click="filter = 'urgent'"
          >
            紧急（30 天内） <b>{{ urgentCount }}</b>
          </button>
          <button
            v-for="bucket in visibleBuckets"
            :key="bucket.key"
            type="button"
            class="bucket"
            :class="{ active: filter === bucket.key }"
            @click="filter = bucket.key"
          >
            {{ bucket.label }} <b>{{ bucket.count }}</b>
          </button>
        </div>

        <div v-if="!filteredItems.length" class="notice notice-ok stack-top">
          这一档没有需要处理的合同。
        </div>
        <div v-else class="table-scroll stack-top">
          <table class="data-table expiry-table">
            <thead>
              <tr>
                <th>供应商</th>
                <th>合同期</th>
                <th style="width: 110px">到期日</th>
                <th style="width: 110px">剩余</th>
                <th style="width: 120px">合同号</th>
                <th style="width: 150px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredItems" :key="item.supplier">
                <td>
                  <b>{{ item.supplier }}</b>
                  <span v-if="item.pending" class="tag tag-plain">需核对</span>
                  <div v-if="item.last_sign_date" class="hint">
                    最近签约 {{ item.last_sign_date }}
                  </div>
                </td>
                <td class="muted">{{ periodText(item) }}</td>
                <td>{{ item.end_date ? cnDate(item.end_date) : '未登记' }}</td>
                <td :class="leftClass(item)">{{ leftText(item.end_date) }}</td>
                <td class="muted">{{ item.contract_no || '—' }}</td>
                <td class="cell-ops">
                  <button type="button" class="btn-link" @click="renew(item)">续签</button>
                  <button type="button" class="btn-link" @click="openTerm(item)">
                    {{ item.end_date ? '修改期限' : '登记期限' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <div v-if="termOpen" class="modal-mask" @click.self="closeTerm">
      <div class="modal-panel term-panel">
        <div class="modal-title">登记合同期限</div>
        <div class="hint">{{ termForm.supplier }}</div>
        <div class="field">
          <label class="field-label">起始日期（可不填）</label>
          <input v-model="termForm.start_date" type="date" />
        </div>
        <div class="field">
          <label class="field-label">到期日期</label>
          <input v-model="termForm.end_date" type="date" />
        </div>
        <div class="field">
          <label class="field-label">备注（可不填）</label>
          <input v-model="termForm.note" placeholder="如：续签待用印 / 按 1 年推算" />
        </div>
        <div v-if="termError" class="notice notice-error">{{ termError }}</div>
        <div class="modal-actions">
          <button
            v-if="canDeleteTerm"
            type="button"
            class="btn btn-ghost btn-danger"
            :disabled="termSaving"
            @click="deleteTermEntry"
          >
            撤销登记
          </button>
          <span class="spacer"></span>
          <button type="button" class="btn btn-ghost" @click="closeTerm">取消</button>
          <button type="button" class="btn btn-primary" :disabled="termSaving" @click="submitTerm">
            {{ termSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
