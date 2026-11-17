<script setup>
import { computed, onMounted, ref } from 'vue'
import ContractStatusCard from '../components/ContractStatusCard.vue'
import {
  BACKUP_DOWNLOAD_URL,
  EXPORT_URL,
  backupNow as runBackup,
  fetchBackups,
  fetchSystemInfo,
} from '../api/system'
import { useToast } from '../composables/useToast'
import { fmtSize, formatInt } from '../lib/format'

const { error: toastError, success: toastSuccess } = useToast()

const info = ref(null)
const backups = ref([])
const loading = ref(false)
const backingUp = ref(false)
const error = ref('')
const backupsError = ref('')
const note = ref('')

async function load() {
  loading.value = true
  error.value = ''
  backupsError.value = ''
  try {
    info.value = await fetchSystemInfo()
  } catch (e) {
    info.value = null
    error.value = '系统信息读取失败：' + (e && e.message ? e.message : e)
  }
  try {
    const data = await fetchBackups()
    backups.value = data.items || []
  } catch (e) {
    backups.value = []
    backupsError.value = '备份列表读取失败：' + (e && e.message ? e.message : e)
  }
  loading.value = false
}

const rows = computed(() => {
  const data = info.value
  if (!data) return []
  const db = data.db || {}
  const counts = data.counts || {}
  const schema = data.schema || {}
  const backup = data.backups || {}
  return [
    {
      key: '程序版本',
      value:
        (data.version || '—') +
        (schema.version !== undefined ? '（数据 v' + schema.version + '）' : ''),
    },
    {
      key: '产品 / 供应商',
      value: formatInt(counts.products) + ' 个 / ' + formatInt(counts.suppliers) + ' 家',
    },
    {
      key: '图片',
      value:
        formatInt(counts.with_image) +
        ' 个产品有图（共 ' +
        formatInt(data.media_count) +
        ' 张）',
    },
    {
      key: '数据库',
      value: fmtSize(db.size) + (db.updated_at ? ' · ' + db.updated_at : ''),
    },
    { key: '数据目录', value: data.data_dir || '—', wide: true },
    {
      key: '备份',
      value: backup.count
        ? backup.count + ' 份' + (backup.latest_at ? ' · 最近 ' + backup.latest_at : '')
        : '暂无',
    },
  ]
})

async function backupNow() {
  if (backingUp.value) return
  backingUp.value = true
  note.value = ''
  try {
    const data = await runBackup()
    note.value = data.name ? '已备份：' + data.name : '当前还没有数据库，无需备份'
    toastSuccess(note.value)
    await load()
  } catch (e) {
    const message = '备份失败：' + (e && e.message ? e.message : e)
    note.value = message
    toastError(message)
  } finally {
    backingUp.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page page-narrow">
    <section class="card">
      <div class="card-title">
        本机运行信息
        <button type="button" class="btn btn-ghost btn-sm title-action" :disabled="loading" @click="load">
          {{ loading ? '读取中…' : '刷新' }}
        </button>
      </div>

      <div v-if="error" class="notice notice-error">{{ error }}</div>
      <div v-else-if="!info && loading" class="empty-text">正在读取系统状态…</div>
      <div v-else-if="info" class="kv-list">
        <div v-for="row in rows" :key="row.key" class="kv-row">
          <span class="kv-key">{{ row.key }}</span>
          <span class="kv-val" :class="{ 'kv-wide': row.wide }">{{ row.value }}</span>
        </div>
      </div>

      <div class="actions-left stack-top">
        <button type="button" class="btn btn-primary" :disabled="backingUp" @click="backupNow">
          {{ backingUp ? '备份中…' : '立即备份' }}
        </button>
        <a class="btn btn-ghost" :href="BACKUP_DOWNLOAD_URL" download>下载数据库</a>
        <a class="btn btn-ghost" :href="EXPORT_URL" download>导出数据包</a>
      </div>
      <div v-if="note" class="hint">{{ note }}</div>
    </section>

    <ContractStatusCard />

    <section class="card">
      <div class="card-title">备份列表</div>
      <div v-if="backupsError" class="notice notice-error">{{ backupsError }}</div>
      <div v-else-if="!backups.length" class="empty-text">还没有备份。点上面的「立即备份」生成一份。</div>
      <div v-else class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th style="width: 110px">大小</th>
              <th style="width: 170px">时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in backups" :key="item.name">
              <td class="mono">{{ item.name }}</td>
              <td>{{ fmtSize(item.size) }}</td>
              <td>{{ item.at || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="hint">
        数据库只保存产品、供应商和合同记录；图片在 data/media，导出数据包会一起打包。
      </div>
    </section>
  </div>
</template>
