<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [Object, String], default: null },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  search: { type: Function, required: true },
  optionTitle: { type: Function, required: true },
  optionDetail: { type: Function, default: null },
  itemKey: { type: Function, default: null },
  delay: { type: Number, default: 150 },
})

const emit = defineEmits(['update:modelValue', 'clear', 'edit'])

const root = ref(null)
const inputValue = ref(props.modelValue ? props.optionTitle(props.modelValue) : '')
const results = ref([])
const open = ref(false)
const loading = ref(false)
const error = ref('')

let timer = null
let seq = 0
let selfClearing = false

function keyOf(item) {
  return props.itemKey ? props.itemKey(item) : props.optionTitle(item)
}

function close() {
  open.value = false
}

function runSearch(q) {
  const current = ++seq
  loading.value = true
  error.value = ''
  Promise.resolve(props.search(q))
    .then((list) => {
      if (current !== seq) return
      results.value = list || []
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
  const value = event.target.value
  inputValue.value = value
  if (props.modelValue && value !== props.optionTitle(props.modelValue)) {
    selfClearing = true
    emit('update:modelValue', null)
    nextTick(() => {
      selfClearing = false
    })
    // 文本一改动就通知父组件，用于立即提示“会清空订单”
    if (value.trim()) emit('edit')
  }
  clearTimeout(timer)
  const q = value.trim()
  if (!q) {
    results.value = []
    open.value = false
    return
  }
  timer = setTimeout(() => {
    open.value = true
    runSearch(q)
  }, props.delay)
}

function onFocus() {
  open.value = true
  const q = inputValue.value.trim()
  if (q && !results.value.length) runSearch(q)
}

function pick(item) {
  emit('update:modelValue', item)
  inputValue.value = props.optionTitle(item)
  results.value = []
  open.value = false
}

function clearSelection() {
  inputValue.value = ''
  results.value = []
  open.value = false
  emit('update:modelValue', null)
  emit('clear')
}

function onBlur() {
  // 用户把输入框删空后离开，视为取消选择；先交给父组件决定是否确认
  if (!inputValue.value.trim() && props.modelValue) emit('clear')
}

function pickFirst() {
  if (open.value && results.value.length) pick(results.value[0])
}

function onDocClick(event) {
  if (root.value && !root.value.contains(event.target)) close()
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      inputValue.value = props.optionTitle(value)
      results.value = []
      open.value = false
    } else if (!selfClearing) {
      inputValue.value = ''
      results.value = []
    }
  },
)

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  clearTimeout(timer)
})
</script>

<template>
  <div ref="root" class="search-select">
    <label v-if="label" class="field-label">{{ label }}</label>
    <div class="search-input-wrap">
      <input
        :value="inputValue"
        :placeholder="placeholder"
        autocomplete="off"
        @input="onInput"
        @focus="onFocus"
        @blur="onBlur"
        @keydown.enter.prevent="pickFirst"
        @keydown.esc="close"
      />
      <button
        v-if="modelValue"
        type="button"
        class="search-clear"
        title="取消选择"
        @mousedown.prevent
        @click="clearSelection"
      >
        ×
      </button>
    </div>
    <div v-if="open" class="search-results">
      <div v-if="loading" class="sr-empty">正在搜索…</div>
      <div v-else-if="error" class="sr-empty sr-error">{{ error }}</div>
      <div v-else-if="!results.length" class="sr-empty">无匹配结果</div>
      <template v-else>
        <button
          v-for="item in results"
          :key="keyOf(item)"
          type="button"
          class="sr-item"
          @click="pick(item)"
        >
          <div class="sr-title">{{ optionTitle(item) }}</div>
          <div v-if="optionDetail && optionDetail(item)" class="sr-detail">{{ optionDetail(item) }}</div>
        </button>
      </template>
    </div>
  </div>
</template>
