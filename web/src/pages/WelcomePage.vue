<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ProgressBar from '../components/ProgressBar.vue'
import { fetchSetupStatus, pickFolder, restoreBackup, startSetupImport } from '../api/setup'
import { useCatalog } from '../composables/useCatalog'
import { useToast } from '../composables/useToast'

const router = useRouter()
const { loadMeta } = useCatalog()
const { success: toastSuccess } = useToast()

const status = ref({
  state: 'idle',
  products: 0,
  need_setup: true,
  done: 0,
  total: 0,
  message: '',
  error: '',
})
const path = ref('')
const picking = ref(false)
const importing = ref(false)
const restoring = ref(false)
const error = ref('')
const note = ref('')
const file = ref(null)
const restoreAck = ref(false)
const restoreResult = ref(null)

let timer = null
let disposed = false
let navigated = false

const running = computed(() => status.value.state === 'running')
const hasData = computed(() => (status.value.products || 0) > 0)

function schedule(delay = 800) {
  clearTimeout(timer)
  if (disposed) return
  timer = setTimeout(refresh, delay)
}

async function refresh() {
  if (disposed) return
  try {
    const data = await fetchSetupStatus()
    status.value = data
    if (data.state === 'running') {
      schedule()
    } else if (data.state === 'done' && data.products > 0 && !navigated) {
      navigated = true
      note.value = '导入完成，正在进入系统…'
      loadMeta(true).catch(() => {})
      setTimeout(() => {
        if (!disposed) router.replace('/order')
      }, 1500)
    }
  } catch (e) {
    if (status.value.state === 'running') schedule(1600)
  }
}

async function chooseFolder() {
  if (picking.value || running.value) return
  picking.value = true
  error.value = ''
  try {
    const data = await pickFolder()
    if (data.path) path.value = data.path
  } catch (e) {
    error.value = '打开选择框失败：' + (e && e.message ? e.message : e) + '（可以直接粘贴文件夹路径）'
  } finally {
    picking.value = false
  }
}

async function startImport() {
  if (!path.value.trim() || importing.value || running.value) return
  importing.value = true
  error.value = ''
  note.value = ''
  try {
    await startSetupImport(path.value.trim())
    status.value = { ...status.value, state: 'running', message: '正在准备…', error: '' }
    schedule()
  } catch (e) {
    error.value = '启动导入失败：' + (e && e.message ? e.message : e)
  } finally {
    importing.value = false
  }
}

function onFile(event) {
  file.value = (event.target.files || [])[0] || null
  restoreAck.value = false
  error.value = ''
  restoreResult.value = null
}

async function doRestore() {
  if (!file.value || restoring.value) return
  if (!restoreAck.value) {
    error.value = '请先勾选「我已知晓恢复会覆盖当前数据」。'
    return
  }
  restoring.value = true
  error.value = ''
  note.value = ''
  try {
    const data = await restoreBackup(file.value)
    restoreResult.value = data
    status.value = { ...status.value, state: 'done', products: data.products || 0, need_setup: false }
    note.value = `恢复完成：${data.products || 0} 个产品，${data.media || 0} 张图片。`
    toastSuccess('数据恢复完成，正在进入系统…')
    loadMeta(true).catch(() => {})
    setTimeout(() => {
      if (!disposed) router.replace('/order')
    }, 1800)
  } catch (e) {
    error.value = '恢复失败：' + (e && e.message ? e.message : e)
  } finally {
    restoring.value = false
  }
}

function goOrder() {
  router.replace('/order')
}

onMounted(refresh)

onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <div class="page page-narrow">
    <div class="welcome-hero">
      <h1>欢迎使用采购下单系统</h1>
      <p>先把你自己的合同导入进来，之后每天打开就能直接下单。</p>
    </div>

    <section v-if="hasData" class="card card-ok">
      <div class="card-title">数据已就绪</div>
      <div class="desc">
        当前已有 <span class="tag tag-green">{{ status.products }} 个产品</span>，可以直接进入系统。
      </div>
      <button type="button" class="btn btn-primary" @click="goOrder">进入系统 →</button>
    </section>

    <template v-else>
      <section class="card">
        <div class="card-title"><span class="step">1</span>导入你的合同</div>
        <div class="desc">
          从易快报把合同附件导出到一个文件夹（.docx），然后选中它。系统会读取合同里的产品、供应商、历史价格和图片。
        </div>
        <div class="inline-row">
          <input
            v-model="path"
            class="grow"
            placeholder="粘贴合同文件夹路径，或点右侧「浏览…」"
            :disabled="running"
          />
          <button type="button" class="btn btn-ghost" :disabled="running || picking" @click="chooseFolder">
            {{ picking ? '选择中…' : '浏览…' }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="running || importing || !path.trim()"
            @click="startImport"
          >
            {{ running ? '导入中…' : '开始导入' }}
          </button>
        </div>

        <template v-if="running || status.state === 'error' || status.state === 'done'">
          <ProgressBar :done="status.done || 0" :total="status.total || 0" :running="running" />
          <div v-if="status.message" class="progress-text">{{ status.message }}</div>
          <div v-if="status.error" class="notice notice-error">
            导入失败：{{ status.error }}（原数据未改动）
          </div>
          <div v-if="status.state === 'done' && hasData" class="notice notice-ok stack-top">
            导入完成，共 {{ status.products }} 个产品。
            <button type="button" class="btn btn-primary btn-sm" @click="goOrder">进入系统 →</button>
          </div>
        </template>

        <div class="hint">
          合同多的时候要几分钟，页面会一直显示进度，不要关闭。<br />
          导入过程中不会动你原来的数据；解析失败的合同会报告原因。
        </div>
      </section>

      <div class="divider">— 或者 —</div>

      <section class="card">
        <div class="card-title"><span class="step">2</span>已有数据备份？直接恢复</div>
        <div class="desc">
          如果你之前用过这个系统，选一个备份的 <b>.db</b> 文件或 <b>数据包 .zip</b> 恢复即可。恢复前会自动备份当前数据库。
        </div>
        <div class="inline-row">
          <input type="file" accept=".db,.zip" :disabled="restoring" @change="onFile" />
          <button type="button" class="btn btn-primary" :disabled="!file || restoring" @click="doRestore">
            {{ restoring ? '恢复中…' : '恢复这个备份' }}
          </button>
        </div>
        <label class="checkbox-line">
          <input v-model="restoreAck" type="checkbox" :disabled="!file || restoring" />
          我已知晓恢复会覆盖当前数据（系统会先自动备份）。
        </label>
        <div v-if="error" class="notice notice-error">{{ error }}</div>
        <div v-if="note" class="notice notice-ok stack-top">{{ note }}</div>
        <div v-if="restoreResult" class="hint">
          已恢复 {{ restoreResult.products || 0 }} 个产品、{{ restoreResult.media || 0 }} 张图片。
        </div>
        <div class="hint">数据包包含数据库和产品图片；单个 .db 只有数据、没有图片。</div>
      </section>
    </template>

    <div class="footer-note">
      所有数据只保存在本机的 data 目录，不会上传到任何服务器。<br />
      导入完成后，双击「采购下单系统」快捷方式即可日常使用。
    </div>
  </div>
</template>
