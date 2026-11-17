import { ref } from 'vue'
import { fetchMeta, searchSuppliers } from '../api/catalog'

// 目录元信息在页面间共享，避免每次切页都重新拉一遍。
const meta = ref({ products: 0, suppliers: 0, with_image: 0, updated: '', revision: 0 })
const metaLoaded = ref(false)
const metaLoading = ref(false)

export function useCatalog() {
  async function loadMeta(force = false) {
    if (metaLoaded.value && !force) return meta.value
    if (metaLoading.value) return meta.value
    metaLoading.value = true
    try {
      const data = await fetchMeta()
      meta.value = {
        products: data.products || 0,
        suppliers: data.suppliers || 0,
        with_image: data.with_image || 0,
        updated: data.updated || '',
        revision: data.revision || 0,
      }
      metaLoaded.value = true
      return meta.value
    } finally {
      metaLoading.value = false
    }
  }

  async function findSuppliers(q = '') {
    const data = await searchSuppliers(q)
    return data.items || []
  }

  return { meta, metaLoaded, metaLoading, loadMeta, findSuppliers }
}
