<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import ContractStatusCard from '../components/ContractStatusCard.vue'
import {
  BACKUP_DOWNLOAD_URL,
  EXPORT_URL,
  backupNow as runBackup,
  fetchBackups,
  fetchSystemInfo,
} from '../api/system'
import {
  fetchDuplicateSuppliers,
  fetchPartyA,
  mergeSuppliers,
  savePartyA,
} from '../api/catalog'
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
const partyAList = ref([])
const partyAIndex = ref(0)
const partySaving = ref(false)
const partiesError = ref('')
const duplicates = ref([])
const duplicatesError = ref('')
const merging = ref('')
const partyForm = reactive({
  name: '',
  short: '',
  credit_code: '',
  contact: '',
  tel: '',
  email: '',
  addr: '',
})

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

function fillPartyForm() {
  const item = partyAList.value[partyAIndex.value]
  if (!item) return
  Object.keys(partyForm).forEach((key) => {
    partyForm[key] = item[key] || ''
  })
}

async function loadParties() {
  partiesError.value = ''
  try {
    const data = await fetchPartyA()
    partyAList.value = data.items || []
    if (partyAIndex.value >= partyAList.value.length) partyAIndex.value = 0
    fillPartyForm()
  } catch (e) {
    partiesError.value = '甲方信息读取失败：' + (e && e.message ? e.message : e)
  }
}

async function saveParty() {
  if (partySaving.value || !partyForm.name) return
  partySaving.value = true
  try {
    await savePartyA({ ...partyForm })
    toastSuccess('甲方信息已保存')
    await loadParties()
  } catch (e) {
    toastError('保存失败：' + (e && e.message ? e.message : e))
  } finally {
    partySaving.value = false
  }
}

async function loadDuplicates() {
  duplicatesError.value = ''
  try {
    const data = await fetchDuplicateSuppliers()
    duplicates.value = data.items || []
  } catch (e) {
    duplicates.value = []
    duplicatesError.value = '重复供应商读取失败：' + (e && e.message ? e.message : e)
  }
}

async function doMerge(item) {
  if (merging.value) return
  const text = `把「${item.source.name}」并入「${item.target.name}」？合并前会自动备份。`
  if (!window.confirm(text)) return
  merging.value = item.source.name
  try {
    await mergeSuppliers(item.source.name, item.target.name)
    toastSuccess('供应商已合并')
    await Promise.all([loadDuplicates(), load()])
  } catch (e) {
    toastError('合并失败：' + (e && e.message ? e.message : e))
  } finally {
    merging.value = ''
  }
}

onMounted(() => {
  load()
  loadParties()
  loadDuplicates()
})
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

    <section class="card">
      <div class="card-title">甲方信息</div>
      <div v-if="partiesError" class="notice notice-error">{{ partiesError }}</div>
      <div v-else-if="!partyAList.length" class="empty-text">正在读取甲方信息…</div>
      <template v-else>
        <div class="field">
          <label class="field-label">公司</label>
          <select v-model="partyAIndex" @change="fillPartyForm">
            <option v-for="(item, index) in partyAList" :key="item.name" :value="index">
              {{ item.name }}
            </option>
          </select>
        </div>
        <div class="form-grid">
          <div class="field">
            <label class="field-label">简称</label>
            <input v-model="partyForm.short" />
          </div>
          <div class="field">
            <label class="field-label">统一社会信用代码</label>
            <input v-model="partyForm.credit_code" />
          </div>
          <div class="field">
            <label class="field-label">联系人</label>
            <input v-model="partyForm.contact" />
          </div>
          <div class="field">
            <label class="field-label">联系电话</label>
            <input v-model="partyForm.tel" />
          </div>
          <div class="field">
            <label class="field-label">联系邮箱</label>
            <input v-model="partyForm.email" />
          </div>
          <div class="field full">
            <label class="field-label">联系地址</label>
            <input v-model="partyForm.addr" />
          </div>
        </div>
        <div class="actions-left stack-top">
          <button type="button" class="btn btn-primary" :disabled="partySaving" @click="saveParty">
            {{ partySaving ? '保存中…' : '保存甲方信息' }}
          </button>
        </div>
      </template>
    </section>

    <section class="card">
      <div class="card-title">供应商去重</div>
      <div v-if="duplicatesError" class="notice notice-error">{{ duplicatesError }}</div>
      <div v-else-if="!duplicates.length" class="empty-text">没有发现“短名 / 全称”候选。</div>
      <div v-else class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>并入（短名）</th>
              <th>保留（全称）</th>
              <th style="width: 110px">产品 / 合同</th>
              <th style="width: 80px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in duplicates" :key="item.source.name + '|' + item.target.name">
              <td>{{ item.source.name }}</td>
              <td>{{ item.target.name }}</td>
              <td class="muted">{{ item.source.products }} / {{ item.source.contracts }}</td>
              <td class="cell-ops">
                <button type="button" class="btn-link" :disabled="!!merging" @click="doMerge(item)">
                  合并
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="hint">只合并确认属于同一家的记录；合并前自动备份，合并记录写入日志。</div>
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
