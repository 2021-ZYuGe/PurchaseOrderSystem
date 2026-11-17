// 通用格式化与金额换算。金额统一用整数分计算，展示时再除 100。
export function formatMoney(value) {
  const n = Number(value)
  return (Number.isFinite(n) ? n : 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatMoney0(value) {
  const n = Number(value)
  return (Number.isFinite(n) ? n : 0).toLocaleString('zh-CN', {
    maximumFractionDigits: 0,
  })
}

export function formatInt(value) {
  const n = Number(value)
  return (Number.isFinite(n) ? n : 0).toLocaleString('zh-CN')
}

export function formatCents(cents) {
  return formatMoney((Number(cents) || 0) / 100)
}

export function inputToCents(value) {
  const raw = String(value ?? '').replace(/,/g, '').trim()
  if (!raw) return 0
  const n = parseFloat(raw)
  return Number.isFinite(n) ? Math.round(n * 100) : 0
}

export function amountCents(unitPrice, qty) {
  const price = inputToCents(unitPrice)
  const count = parseInt(qty, 10)
  return price * (Number.isFinite(count) ? count : 0)
}

export function todayISO() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function cnDate(iso) {
  const parts = String(iso || '').split('-')
  if (parts.length !== 3 || !parts[0]) return String(iso || '')
  return `${parts[0]}年${parseInt(parts[1], 10) || ''}月${parseInt(parts[2], 10) || ''}日`
}

export function cnDateShort(iso) {
  const text = String(iso || '').slice(0, 10)
  return text || '—'
}

export function daysLeft(iso) {
  if (!iso) return null
  const target = new Date(String(iso).slice(0, 10) + 'T00:00:00')
  if (Number.isNaN(target.getTime())) return null
  const now = new Date(todayISO() + 'T00:00:00')
  return Math.round((target - now) / 86400000)
}

export function fmtSize(bytes) {
  const n = Number(bytes || 0)
  if (!n) return '—'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

export function mediaUrl(file) {
  if (!file) return ''
  if (/^(https?:|data:|blob:)/.test(file)) return file
  if (file.startsWith('/')) return file
  return '/media/' + encodeURIComponent(file)
}

export function resolveOutputUrl(url) {
  if (!url) return ''
  if (/^https?:/.test(url)) return url
  return url.startsWith('/') ? url : '/' + url
}

export function dateDigits(text) {
  return String(text || '').replace(/\D/g, '')
}
