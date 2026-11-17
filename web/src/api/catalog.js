import { getJSON, postJSON } from './client'

export function fetchMeta() {
  return getJSON('/api/catalog/meta')
}

export function searchProducts({ q = '', supplier = '', limit = 20 } = {}) {
  return getJSON('/api/products', { query: { q, supplier, limit } })
}

export function searchSuppliers(q = '') {
  return getJSON('/api/suppliers', { query: { q } })
}

export function fetchArchive(name = '') {
  return getJSON('/api/suppliers/archive', { query: { name } })
}

export function saveArchive(profile) {
  return postJSON('/api/suppliers/archive', profile)
}
