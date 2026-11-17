import { ref } from 'vue'

const KEY = 'payThreshold'
const DEFAULT_THRESHOLD = 70000

function readThreshold() {
  const value = parseFloat(localStorage.getItem(KEY))
  return Number.isFinite(value) && value >= 0 ? value : DEFAULT_THRESHOLD
}

const threshold = ref(readThreshold())

export function usePayThreshold() {
  function setThreshold(value) {
    const n = parseFloat(value)
    threshold.value = Number.isFinite(n) && n >= 0 ? n : 0
    try {
      localStorage.setItem(KEY, String(threshold.value))
    } catch (e) {
      /* 忽略隐私模式下的写入失败 */
    }
  }

  return { threshold, setThreshold, DEFAULT_THRESHOLD }
}
