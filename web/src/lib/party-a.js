// 甲方目录：后端是唯一来源，localStorage 只记“上次选了哪家”。
import { fetchPartyA } from '../api/catalog'

const SELECTED_KEY = 'partyASelected'
let cache = null
let pending = null

export function selectedPartyAName() {
  try {
    return localStorage.getItem(SELECTED_KEY) || ''
  } catch (e) {
    return ''
  }
}

export function rememberPartyA(name) {
  try {
    localStorage.setItem(SELECTED_KEY, name || '')
  } catch (e) {
    /* 忽略 */
  }
}

export async function loadPartyA(force = false) {
  if (cache && !force) return cache
  if (!pending || force) {
    pending = fetchPartyA()
      .then((data) => {
        cache = data.items || []
        return cache
      })
      .finally(() => {
        pending = null
      })
  }
  return pending
}

export function pickPartyA(list, name) {
  if (!list || !list.length) return null
  return list.find((item) => item.name === name) || list[0]
}
