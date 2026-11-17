import { ref } from 'vue'
import { fetchExpiry } from '../api/contracts'

// 到期数据在合同页和下单页共享；跨天或保存期限后调用 load(true) 刷新。
const expiry = ref(null)
const loading = ref(false)
const error = ref('')
const loadedAt = ref(0)

export function useExpiry() {
  async function load(force = false) {
    if (!force && expiry.value && Date.now() - loadedAt.value < 60000) return expiry.value
    if (loading.value) return expiry.value
    loading.value = true
    error.value = ''
    try {
      expiry.value = await fetchExpiry()
      loadedAt.value = Date.now()
      return expiry.value
    } catch (e) {
      error.value = e && e.message ? e.message : String(e)
      return expiry.value
    } finally {
      loading.value = false
    }
  }

  function findExpiry(name) {
    const items = (expiry.value && expiry.value.items) || []
    return items.find((item) => item.supplier === name) || null
  }

  return { expiry, loading, error, load, findExpiry }
}
