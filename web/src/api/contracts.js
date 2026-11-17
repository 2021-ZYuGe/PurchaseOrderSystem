import { deleteJSON, getJSON, postJSON } from './client'

export function fetchExpiry() {
  return getJSON('/api/contracts/expiry')
}

export function fetchContractStatus() {
  return getJSON('/api/contracts/status')
}

export function searchContracts(q, limit = 50) {
  return getJSON('/api/contracts/search', { query: { q, limit } })
}

export function generateContract(payload) {
  return postJSON('/api/contracts', payload, { timeout: 120000 })
}

export function generateInfoSheet(partyB) {
  return postJSON('/api/contracts/info-sheet', { party_b: partyB }, { timeout: 120000 })
}

export function saveTerm({ supplier, start_date, end_date, note = '' }) {
  return postJSON('/api/contracts/terms', { supplier, start_date, end_date, note })
}

export function removeTerm(supplier) {
  return deleteJSON('/api/contracts/terms', { query: { supplier } })
}
