<script setup>
import { useToast } from '../composables/useToast'

const { toasts, remove } = useToast()
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="'toast-' + t.type"
      role="status"
      @click="remove(t.id)"
    >
      {{ t.message }}
    </div>
  </div>
</template>
