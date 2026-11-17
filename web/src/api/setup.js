import { getJSON, postBinary, postJSON } from './client'

export function fetchSetupStatus() {
  return getJSON('/api/setup/status')
}

export function startSetupImport(path) {
  return postJSON('/api/setup/import', { path })
}

export function pickFolder() {
  return postJSON('/api/setup/pick-folder', {}, { timeout: 600000 })
}

export function restoreBackup(file) {
  return postBinary('/api/setup/restore', file, { timeout: 300000 })
}
