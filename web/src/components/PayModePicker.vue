<script setup>
import { computed, watch } from 'vue'
import { formatCents, formatMoney0 } from '../lib/format'
import { payTextPreview } from '../lib/order-docs'

const props = defineProps({
  modelValue: { type: String, default: '' },
  totalCents: { type: Number, default: 0 },
  threshold: { type: Number, default: 70000 },
})

const emit = defineEmits(['update:modelValue', 'update:threshold'])

const options = [
  { key: 'full', title: '全额付款', desc: '合同签订后按约定期限支付 100% 货款' },
  { key: 'p30', title: '30% 预付款 + 70% 尾款', desc: '签订后付 30% 预付款，生产完成后付 70% 尾款' },
  { key: 'p50', title: '50% 预付款 + 50% 尾款', desc: '签订后付 50% 预付款，生产完成后付 50% 尾款' },
]

const thresholdCents = computed(() => Math.round(props.threshold * 100))
const below = computed(() => props.totalCents < thresholdCents.value)

const note = computed(() => {
  if (!props.totalCents) return '填写单价和数量后，这里会显示可选的付款方式。'
  if (below.value) {
    return `当前总金额 ${formatCents(props.totalCents)} 元 ＜ ${formatMoney0(props.threshold)} 元，未达到预付款起订金额，只能全额付款。`
  }
  return `当前总金额 ${formatCents(props.totalCents)} 元 ≥ ${formatMoney0(props.threshold)} 元，可选择 30% 或 50% 预付款方式。`
})

function disabled(key) {
  return below.value && key !== 'full'
}

function select(key) {
  if (disabled(key)) return
  emit('update:modelValue', key)
}

function onThreshold(event) {
  emit('update:threshold', event.target.value)
}

watch(
  [below, () => props.totalCents],
  () => {
    // 空单保持未选中；一旦有金额且低于阈值，再自动落到全款
    if (props.totalCents > 0 && below.value && props.modelValue !== 'full') {
      emit('update:modelValue', 'full')
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="pay-picker">
    <div class="pay-threshold">
      <label for="payThresholdInput">预付款起订金额</label>
      <input
        id="payThresholdInput"
        type="number"
        min="0"
        step="1000"
        :value="threshold"
        @input="onThreshold"
      />
      <span class="unit">元：订单总额达到此金额，才可选择 30% / 50% 预付款</span>
    </div>

    <div class="pay-options">
      <button
        v-for="opt in options"
        :key="opt.key"
        type="button"
        class="pay-opt"
        :class="{ active: modelValue === opt.key, disabled: disabled(opt.key) }"
        :disabled="disabled(opt.key)"
        @click="select(opt.key)"
      >
        <span class="pt">{{ opt.title }}</span>
        <span class="pd">{{ opt.desc }}</span>
      </button>
    </div>

    <div class="pay-note">{{ note }}</div>
    <div v-if="totalCents && modelValue" class="hint">
      付款方案：{{ payTextPreview(totalCents, modelValue) }}
    </div>
  </div>
</template>
