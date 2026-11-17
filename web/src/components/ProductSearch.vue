<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { searchProducts } from '../api/catalog'
import { mediaUrl } from '../lib/format'

const props = defineProps({
  supplierId: { type: String, default: '' },
  supplierProductIds: { type: Array, default: () => [] },
  placeholder: { type: String, default: '输入产品名称搜索，可添加多个产品' },
})

const emit = defineEmits(['pick'])

const root = ref(null)
const keyword = ref('')
const results = ref([])
const open = ref(false)
const loading = ref(false)
const error = ref('')

let timer = null
let seq = 0

const productIdSet = computed(() => new Set(props.supplierProductIds || []))

function close() {
  open.value = false
}

function run(raw) {
  const current = ++seq
  loading.value = true
  error.value = ''
  searchProducts({ q: raw, supplier: props.supplierId, limit: 20 })
    .then((data) => {
      if (current !== seq) return
      results.value = data.items || []
    })
    .catch((e) => {
      if (current !== seq) return
      results.value = []
      error.value = e && e.message ? e.message : String(e)
    })
    .finally(() => {
      if (current === seq) loading.value = false
    })
}

function onInput(event) {
  const raw = event.target.value
  keyword.value = raw
  clearTimeout(timer)
  if (!raw.trim()) {
    results.value = []
    open.value = false
    return
  }
  timer = setTimeout(() => {
    open.value = true
    run(raw.trim())
  }, 120)
}

function onFocus() {
  open.value = true
  if (keyword.value.trim() && !results.value.length) run(keyword.value.trim())
}

function pick(product) {
  emit('pick', product)
  keyword.value = ''
  results.value = []
  open.value = false
}

function detailOf(product) {
  const parts = []
  const aliases = product.aliases || []
  if (aliases.length) parts.push('别名 ' + aliases.join('、'))
  if (product.spec) parts.push('规格 ' + product.spec)
  const prices = product.prices || []
  parts.push('历史价 ' + (prices.length ? prices.map((p) => '¥' + p).join('/') : '—'))
  parts.push('下单' + (product.order_count || 0) + '次')
  return parts.join(' · ')
}

function onDocClick(event) {
  if (root.value && !root.value.contains(event.target)) close()
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  clearTimeout(timer)
})
</script>

<template>
  <div ref="root" class="search-select product-search">
    <input
      :value="keyword"
      :placeholder="placeholder"
      autocomplete="off"
      @input="onInput"
      @focus="onFocus"
      @keydown.esc="close"
    />
    <div v-if="open" class="search-results product-results">
      <div v-if="loading" class="sr-empty">正在搜索…</div>
      <div v-else-if="error" class="sr-empty sr-error">搜索失败：{{ error }}</div>
      <div v-else-if="!results.length" class="sr-empty">无匹配结果</div>
      <template v-else>
        <button
          v-for="product in results"
          :key="product.id"
          type="button"
          class="sr-item sr-product"
          @click="pick(product)"
        >
          <img v-if="product.image" class="thumb" :src="mediaUrl(product.image)" alt="" />
          <span v-else class="thumb thumb-empty">无图</span>
          <span class="sr-body">
            <span class="sr-title">
              {{ product.name }}
              <span v-if="productIdSet.has(product.id)" class="tag">该供应商产品</span>
              <span v-if="(product.images || []).length > 1" class="tag tag-plain">
                {{ product.images.length }} 图
              </span>
            </span>
            <span class="sr-detail">{{ detailOf(product) }}</span>
          </span>
        </button>
      </template>
    </div>
  </div>
</template>
