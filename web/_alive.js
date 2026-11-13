/* 页面在线信号：让本地服务知道网页还开着。
 * 页面关掉 → 这条长连接断开 → 服务端等 10 秒确认没人了，就自动关掉系统。
 * 刷新页面时会在宽限期内重新连上，不会误关。
 * 任何异常都静默处理，绝不影响页面正常使用。
 */
(function () {
  try {
    if (location.protocol !== 'http:' && location.protocol !== 'https:') return;
    var host = location.hostname;
    if (host !== '127.0.0.1' && host !== 'localhost') return;
    // 自动化测试/截图时加 ?noalive=1，避免长连接让页面一直处于"加载中"
    if (/[?&]noalive=1/.test(location.search)) return;

    var CID = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    var es = null;
    var said = false;

    function connect() {
      try {
        if (typeof EventSource === 'undefined') return;
        es = new EventSource('/__alive?id=' + CID);
        es.onerror = function () {
          // 服务端关闭或网络抖动时浏览器会自己重连，这里不用管
        };
      } catch (e) {}
    }

    function bye() {
      if (said) return;
      said = true;
      try {
        var url = '/__bye?id=' + CID + '&t=' + Date.now();
        if (navigator.sendBeacon) navigator.sendBeacon(url);
        else fetch(url, { cache: 'no-store' });
      } catch (e) {}
      try { if (es) es.close(); } catch (e) {}
    }

    // 关闭标签页、关浏览器、跳转都会触发；刷新也触发，但服务端有 10 秒宽限期
    window.addEventListener('pagehide', bye);
    window.addEventListener('beforeunload', bye);

    connect();
  } catch (e) {}
})();
