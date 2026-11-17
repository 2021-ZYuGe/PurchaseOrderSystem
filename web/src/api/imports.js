import { getJSON, postJSON } from './client'

export function previewEkb(payload) {
  return postJSON('/api/imports/ekuaibao/preview', payload, { timeout: 300000 })
}

export function startEkb(payload) {
  return postJSON('/api/imports/ekuaibao', payload, { timeout: 60000 })
}

export function startFolder(path) {
  return postJSON('/api/imports/folder', { path }, { timeout: 60000 })
}

export function fetchCurrentImport() {
  return getJSON('/api/imports/current')
}

export function fetchImportHistory(limit = 10) {
  return getJSON('/api/imports/history', { query: { limit } })
}
