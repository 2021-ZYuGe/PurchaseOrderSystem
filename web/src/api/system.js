import { getJSON, postJSON } from './client'

export function fetchSystemInfo() {
  return getJSON('/api/system/info')
}

export function fetchBackups() {
  return getJSON('/api/system/backups')
}

export function backupNow() {
  return postJSON('/api/system/backup', {}, { timeout: 120000 })
}

export const BACKUP_DOWNLOAD_URL = '/api/system/backup/download'
export const EXPORT_URL = '/api/system/export'
