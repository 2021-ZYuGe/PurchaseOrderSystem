<script setup>
import { computed } from 'vue'

const props = defineProps({
  done: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  running: { type: Boolean, default: false },
})

const percent = computed(() => {
  if (!props.total) return 0
  return Math.min(100, Math.max(0, Math.round((props.done / props.total) * 100)))
})

const indeterminate = computed(() => props.running && !props.total)
</script>

<template>
  <div class="progress">
    <div
      class="progress-bar"
      :class="{ indeterminate }"
      :style="indeterminate ? {} : { width: percent + '%' }"
    ></div>
  </div>
</template>
