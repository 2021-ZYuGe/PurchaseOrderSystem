/* 页面在线信号：让本地服务知道网页还开着。
 * 关掉最后一个页签后，服务端等 10 秒确认没人了就自动退出。
 * 只在 127.0.0.1 / localhost 生效，任何异常都静默处理。
 */
export function startKeepalive() {
  try {
    if (location.protocol !== 'http:' && location.protocol !== 'https:') return
    const host = location.hostname
    if (host !== '127.0.0.1' && host !== 'localhost') return
    if (/[?&]noalive=1/.test(location.search)) return

    const id = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    let source = null
    let said = false

    try {
      if (typeof EventSource === 'undefined') return
      source = new EventSource('/__alive?id=' + id)
      source.onerror = () => {
        // 断线由浏览器自动重连，这里不处理
      }
    } catch (e) {
      /* 静默 */
    }

    const bye = () => {
      if (said) return
      said = true
      try {
        const url = '/__bye?id=' + id + '&t=' + Date.now()
        if (navigator.sendBeacon) navigator.sendBeacon(url)
        else fetch(url, { cache: 'no-store' })
      } catch (e) {
        /* 静默 */
      }
      try {
        if (source) source.close()
      } catch (e) {
        /* 静默 */
      }
    }

    window.addEventListener('pagehide', bye)
    window.addEventListener('beforeunload', bye)
  } catch (e) {
    /* 静默 */
  }
}
