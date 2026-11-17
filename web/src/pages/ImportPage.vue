<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import ProgressBar from '../components/ProgressBar.vue'
import {
  fetchCurrentImport,
  fetchImportHistory,
  previewEkb,
  startEkb,
  startFolder,
} from '../api/imports'
import { pickFolder } from '../api/setup'
import { useCatalog } from '../composables/useCatalog'
import { useToast } from '../composables/useToast'

const { loadMeta } = useCatalog()
const { success: toastSuccess } = useToast()

const tab = ref('ekb')
const url = ref('')
const folder = ref('')
const opts = reactive({
  template: '合同审批流程',
  keyword: '合同',
  since: '',
  scope: 'all',
  limit: 0,
  include_duplicates: false,
})

const preview = ref(null)
const checking = ref(false)
const starting = ref(false)
const picking = ref(false)
const error = ref('')
const showProgress = ref(false)
const history = ref([])
const historyLoading = ref(false)
const status = ref({
  state: 'idle',
  phase: '',
  message: '',
  error: '',
  done: 0,
  total: 0,
  batch: '',
  started: '',
  finished: '',
  products: 0,
  result: null,
})

let timer = null
let disposed = false

const running = computed(() => status.value.state === 'running')
const result = computed(() => status.value.result || null)
const stats = computed(() => (result.value && result.value.stats) || {})
const phaseLabel = computed(() => {
  const map = { listing: '连接并读取单据', downloading: '下载附件', importing: '解析入库' }
  if (status.value.phase && map[status.value.phase]) return map[status.value.phase]
  if (running.value) return '处理中'
  if (status.value.state === 'done') return '已完成'
  return ''
})

function newCount(item) {
  return item ? item.new || 0 : 0
}

function sourceLabel(source) {
  return source === 'ekuaibao' ? '易快报' : source === 'folder' ? '文件夹' : source || '—'
}

function statusLabel(value) {
  return { done: '完成', error: '失败', running: '进行中', idle: '—' }[value] || value || '—'
}

function schedule(delay = 1200) {
  clearTimeout(timer)
  if (disposed) return
  timer = setTimeout(poll, delay)
}

async function poll() {
  if (disposed) return
  try {
    const data = await fetchCurrentImport()
    status.value = data
    if (data.state === 'running') {
      showProgress.value = true
      schedule()
    } else if (showProgress.value) {
      loadHistory()
      loadMeta(true).catch(() => {})
    }
  } catch (e) {
    // 服务忙时缓一下再试，不打断页面
    if (showProgress.value) schedule(2500)
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const data = await fetchImportHistory(10)
    history.value = data.items || []
  } catch (e) {
    /* 历史列表失败不打断当前操作 */
  } finally {
    historyLoading.value = false
  }
}

function payload() {
  return {
    url: url.value.trim(),
    template: opts.template,
    since: opts.since,
    scope: opts.scope,
    limit: Number(opts.limit) || 0,
    keyword: opts.keyword,
    delay: 1.0,
    include_duplicates: !!opts.include_duplicates,
  }
}

async function runPreview() {
  if (checking.value || running.value) return
  checking.value = true
  error.value = ''
  preview.value = null
  try {
    preview.value = await previewEkb(payload())
  } catch (e) {
    error.value = '预览失败：' + (e && e.message ? e.message : e)
  } finally {
    checking.value = false
  }
}

async function runEkbImport() {
  if (!preview.value || starting.value || running.value) return
  if (newCount(preview.value) === 0 && !opts.include_duplicates) {
    error.value = '这批单据都已导入过；确实要重新下载，请勾选「包含重复单据」。'
    return
  }
  starting.value = true
  error.value = ''
  try {
    await startEkb(payload())
    status.value = {
      ...status.value,
      state: 'running',
      phase: 'listing',
      message: '正在连接易快报…',
      error: '',
      done: 0,
      total: 0,
      result: null,
    }
    showProgress.value = true
    toastSuccess('导入任务已启动')
    schedule(800)
  } catch (e) {
    error.value =
      e && e.code === 'import_running'
        ? '已有导入任务在运行，请等它完成后再开始新的任务。'
        : '启动失败：' + (e && e.message ? e.message : e)
  } finally {
    starting.value = false
  }
}

async function chooseFolder() {
  if (picking.value || running.value) return
  picking.value = true
  error.value = ''
  try {
    const data = await pickFolder()
    if (data.path) folder.value = data.path
  } catch (e) {
    error.value = '打开选择框失败：' + (e && e.message ? e.message : e) + '（可以直接粘贴路径）'
  } finally {
    picking.value = false
  }
}

async function runFolderImport() {
  if (!folder.value.trim() || starting.value || running.value) return
  starting.value = true
  error.value = ''
  try {
    await startFolder(folder.value.trim())
    status.value = {
      ...status.value,
      state: 'running',
      phase: 'importing',
      message: '正在解析入库…',
      error: '',
      done: 0,
      total: 0,
      result: null,
    }
    showProgress.value = true
    toastSuccess('导入任务已启动')
    schedule(800)
  } catch (e) {
    error.value =
      e && e.code === 'import_running'
        ? '已有导入任务在运行，请等它完成后再开始新的任务。'
        : '启动失败：' + (e && e.message ? e.message : e)
  } finally {
    starting.value = false
  }
}

function resetPanel() {
  preview.value = null
  error.value = ''
  showProgress.value = false
  status.value = {
    state: 'idle',
    phase: '',
    message: '',
    error: '',
    done: 0,
    total: 0,
    batch: '',
    started: '',
    finished: '',
    products: 0,
    result: null,
  }
}

onMounted(() => {
  loadHistory()
  poll()
})

onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <div class="page page-narrow">
    <section class="card">
      <div class="tab-bar">
        <button
          type="button"
          class="tab"
          :class="{ active: tab === 'ekb' }"
          @click="tab = 'ekb'"
        >
          易快报链接
        </button>
        <button
          type="button"
          class="tab"
          :class="{ active: tab === 'folder' }"
          @click="tab = 'folder'"
        >
          本地文件夹
        </button>
      </div>

      <template v-if="tab === 'ekb'">
        <div class="desc">
          企业微信里打开易快报 → 底部「我的单据」→ 右上角 … → 复制链接，粘贴到这里。<br />
          链接里有登录凭证，只在内存中使用，不会保存到磁盘。
        </div>
        <textarea
          v-model="url"
          class="text-area"
          placeholder="粘贴易快报链接（包含 accessToken 与 ekbCorpId）"
          :disabled="running"
        ></textarea>

        <div class="form-grid stack-top">
          <div class="field">
            <label class="field-label">单据模板</label>
            <input v-model="opts.template" :disabled="running" />
          </div>
          <div class="field">
            <label class="field-label">附件关键字</label>
            <input v-model="opts.keyword" placeholder="留空=全部" :disabled="running" />
          </div>
          <div class="field">
            <label class="field-label">只处理此日期之后</label>
            <input v-model="opts.since" type="date" :disabled="running" />
          </div>
          <div class="field">
            <label class="field-label">单据范围</label>
            <select v-model="opts.scope" :disabled="running">
              <option value="all">全部</option>
              <option value="active">在途</option>
              <option value="done">已完成</option>
              <option value="paid">已支付</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">最多处理</label>
            <input v-model.number="opts.limit" type="number" min="0" :disabled="running" />
          </div>
        </div>

        <div class="actions-left stack-top">
          <button
            type="button"
            class="btn btn-ghost"
            :disabled="running || checking || !url.trim()"
            @click="runPreview"
          >
            {{ checking ? '正在检查…' : '检查链接 / 预览' }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="running || starting || !preview || (newCount(preview) === 0 && !opts.include_duplicates)"
            @click="runEkbImport"
          >
            {{ running ? '导入中…' : '开始导入' }}
          </button>
          <span v-if="!preview" class="hint">先预览，确认新增与重复数量再导入。</span>
        </div>

        <div v-if="error" class="notice notice-error stack-top">{{ error }}</div>

        <div v-if="preview" class="preview-box">
          <div class="stat-line">
            <span>已连接 <b>{{ preview.who || '易快报' }}</b></span>
            <span>匹配单据 <b>{{ preview.matching || 0 }}</b></span>
            <span>新增 <b>{{ newCount(preview) }}</b></span>
            <span class="text-warn">重复 <b>{{ preview.duplicates || 0 }}</b></span>
          </div>
          <div v-if="newCount(preview) === 0" class="desc">
            这批单据都已经导入过了。要重新下载，可以勾选下面的「包含重复单据」。
          </div>
          <div v-if="(preview.samples || []).length" class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 120px">单号</th>
                  <th>标题</th>
                  <th style="width: 110px">提交日期</th>
                  <th style="width: 90px">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="sample in preview.samples" :key="sample.code + sample.flow_id">
                  <td>{{ sample.code }}</td>
                  <td>
                    {{ sample.title }}
                    <span class="tag" :class="sample.is_new ? 'tag-green' : 'tag-warn'">
                      {{ sample.is_new ? '新增' : '已有' }}
                    </span>
                  </td>
                  <td>{{ sample.submit }}</td>
                  <td>{{ sample.state }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <label class="checkbox-line">
            <input v-model="opts.include_duplicates" type="checkbox" />
            包含重复单据（正常不用勾）
          </label>
          <div class="hint">
            每张单据约 1 秒（读取附件地址），几百张需要十几分钟；期间可以离开页面，回来会接着显示进度。
          </div>
        </div>
      </template>

      <template v-else>
        <div class="desc">
          已经手动把合同下载到本地时用这个入口。只做增量导入：已收录的合同会自动跳过。
        </div>
        <div class="inline-row">
          <input
            v-model="folder"
            class="grow"
            placeholder="粘贴合同文件夹路径，或点「浏览…」"
            :disabled="running"
          />
          <button type="button" class="btn btn-ghost" :disabled="running || picking" @click="chooseFolder">
            {{ picking ? '选择中…' : '浏览…' }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="running || starting || !folder.trim()"
            @click="runFolderImport"
          >
            开始导入
          </button>
        </div>
        <div v-if="error" class="notice notice-error stack-top">{{ error }}</div>
        <div class="hint">这里不会清空现有数据，只把新合同追加进来。</div>
      </template>
    </section>

    <section v-if="showProgress || running" class="card">
      <div class="card-title">导入进度</div>
      <ProgressBar :done="status.done || 0" :total="status.total || 0" :running="running" />
      <div class="progress-text">
        <b>{{ phaseLabel }}</b>
        <span v-if="status.total"> · {{ status.done }}/{{ status.total }}</span>
        <span v-if="status.message"> — {{ status.message }}</span>
      </div>
      <div v-if="status.state === 'error'" class="notice notice-error">
        {{ status.error || '导入失败' }}
      </div>

      <div v-if="status.state === 'done' && result" class="notice notice-ok stack-top">
        <div><b>导入完成</b> · 批次 {{ result.id || status.batch }}</div>
        <div class="hint">
          单据 {{ stats.bills_new || 0 }} 张新增 · 附件 {{ stats.attachments || 0 }} 个 ·
          下载 {{ stats.downloaded || 0 }} 个 · 跳过 {{ stats.skipped || 0 }} 个 ·
          失败 {{ stats.failed || 0 }} 个
        </div>
        <div class="actions-inline">
          <RouterLink class="btn btn-primary btn-sm" to="/order">去首页看看 →</RouterLink>
          <button type="button" class="btn btn-ghost btn-sm" @click="resetPanel">再导一批</button>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-title">最近批次</div>
      <div v-if="historyLoading && !history.length" class="empty-text">正在读取导入记录…</div>
      <div v-else-if="!history.length" class="empty-text">还没有导入记录。</div>
      <div v-else class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 160px">时间</th>
              <th style="width: 90px">来源</th>
              <th>结果</th>
              <th style="width: 90px">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in history" :key="item.id">
              <td>{{ item.created }}</td>
              <td>{{ sourceLabel(item.source) }}</td>
              <td>{{ item.message || (item.stats && item.stats.bills_new) || '—' }}</td>
              <td>{{ statusLabel(item.status) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="footer-note">
      导入过程不会改动已收录的合同；失败原因会写进批次目录的 batch.json 与下载记录.csv。
    </div>
  </div>
</template>
