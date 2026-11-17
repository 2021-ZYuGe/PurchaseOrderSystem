<script setup>
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import ToastHost from './components/ToastHost.vue'
import { useCatalog } from './composables/useCatalog'
import { useExpiry } from './composables/useExpiry'
import { fetchSetupStatus } from './api/setup'

const route = useRoute()
const router = useRouter()
const { meta, loadMeta } = useCatalog()
const { expiry, load: loadExpiry } = useExpiry()

const navs = [
  { to: '/order', label: '下单' },
  { to: '/expiry', label: '合同倒计时' },
  { to: '/contract', label: '新增主合同' },
  { to: '/import', label: '导入' },
  { to: '/system', label: '系统状态' },
]

const urgentCount = computed(() => {
  const counts = (expiry.value && expiry.value.counts) || {}
  return (counts.expired || 0) + (counts.d3 || 0) + (counts.d7 || 0) + (counts.d30 || 0)
})

const metaText = computed(() => {
  const data = meta.value
  if (!data.products && !data.suppliers) return '正在读取产品库…'
  const updated = String(data.updated || '').slice(0, 10)
  return (
    `产品库 ${data.products} 项 · 供应商 ${data.suppliers} 家 · 图片 ${data.with_image} 张` +
    (updated ? ` · 数据更新 ${updated}` : '')
  )
})

onMounted(async () => {
  loadMeta(true).catch(() => {})
  loadExpiry().catch(() => {})
  try {
    const status = await fetchSetupStatus()
    if ((status.need_setup || !status.products) && route.name !== 'welcome') {
      router.replace('/welcome')
    }
  } catch (e) {
    // 服务尚未就绪时保持当前页面，不把用户弹来弹去
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <div class="brand-title">采购下单系统</div>
        <div class="brand-sub">兴趣岛 · 本机数据</div>
      </div>
      <nav class="app-nav">
        <RouterLink v-for="item in navs" :key="item.to" :to="item.to" class="nav-link">
          {{ item.label }}
          <span v-if="item.to === '/expiry' && urgentCount" class="nav-badge">
            {{ urgentCount }}
          </span>
        </RouterLink>
      </nav>
      <div class="header-right">
        <div class="header-meta">{{ metaText }}</div>
      </div>
    </header>

    <main class="app-main">
      <RouterView />
    </main>

    <ToastHost />
  </div>
</template>
