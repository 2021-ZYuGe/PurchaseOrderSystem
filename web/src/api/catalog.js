import { getJSON, postJSON, putJSON } from './client'

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

export function fetchPartyA() {
  return getJSON('/api/party-a')
}

export function savePartyA(party) {
  return putJSON('/api/party-a', party)
}

export function fetchDuplicateSuppliers() {
  return getJSON('/api/suppliers/duplicates')
}

export function mergeSuppliers(source, target) {
  return postJSON('/api/suppliers/merge', { source, target })
}
