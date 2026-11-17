<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchContractStatus } from '../api/contracts'

const status = ref(null)
const loading = ref(false)
const error = ref('')

const fresh = computed(() => (status.value && status.value.freshness) || {})
const pending = computed(() => (status.value && status.value.pending) || {})
const samples = computed(() => pending.value.samples || [])
const missingDirs = computed(() => pending.value.missing_dirs || [])

function sampleText(sample) {
  if (sample == null) return ''
  if (typeof sample === 'string') return sample
  return sample.file || sample.name || sample.path || sample.code || JSON.stringify(sample)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await fetchContractStatus()
  } catch (e) {
    error.value = e && e.message ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="card">
    <div class="card-title">
      <span>合同数据</span>
      <button type="button" class="btn btn-ghost btn-sm title-action" :disabled="loading" @click="load">
        {{ loading ? '读取中…' : '刷新' }}
      </button>
    </div>

    <div v-if="error" class="notice notice-error">{{ error }}</div>
    <div v-else-if="!status" class="empty-text">正在读取合同状态…</div>
    <template v-else>
      <div class="kv-list">
        <div class="kv-row">
          <span class="kv-key">数据库更新</span>
          <span class="kv-val">{{ fresh.data_updated_at || '—' }}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">最近导入</span>
          <span class="kv-val">{{ fresh.last_import || '—' }}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">合同台账</span>
          <span class="kv-val">
            {{ fresh.contract_records || 0 }} 份
            <span class="muted">（已导入文件 {{ fresh.imported_files || 0 }} 个）</span>
          </span>
        </div>
        <div class="kv-row">
          <span class="kv-key">最近签约</span>
          <span class="kv-val">
            {{ fresh.last_sign_date || '—' }}
            <span v-if="fresh.last_main_contract_date" class="muted">
              · 主合同 {{ fresh.last_main_contract_date }}
            </span>
          </span>
        </div>
      </div>

      <div v-if="pending.pending_count > 0" class="notice notice-warn stack-top">
        <div>
          发现 <b>{{ pending.pending_count }}</b> 份新合同还没导入
          <span v-if="pending.newest_date">（最新 {{ pending.newest_date }}）</span>。
        </div>
        <div v-if="pending.newest_file" class="hint">{{ pending.newest_file }}</div>
        <ul v-if="samples.length" class="plain-list">
          <li v-for="(s, i) in samples.slice(0, 3)" :key="i">{{ sampleText(s) }}</li>
        </ul>
        <RouterLink class="btn btn-primary btn-sm" to="/import">去导入新合同</RouterLink>
      </div>
      <div v-else-if="missingDirs.length" class="notice notice-muted stack-top">
        合同来源目录未连接（{{ missingDirs.join('、') }}），暂时无法核对是否有更新的合同。
      </div>
      <div v-else-if="pending.checked_at" class="notice notice-ok stack-top">
        已核对合同来源目录，没有未导入的新合同（{{ pending.checked_at }}）。
      </div>
    </template>
  </section>
</template>
