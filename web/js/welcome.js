// 首启向导：导入合同文件夹 / 从数据库备份恢复
// Vue 全局版 + 经典脚本，不依赖首页的 app-core.js。
(function () {
  if (!window.Vue) return;
  const { createApp, ref, computed, onMounted } = Vue;

  async function request(url, opts) {
    const resp = await fetch(url, Object.assign({ cache: 'no-store' }, opts || {}));
    const text = await resp.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      throw new Error('服务返回异常（HTTP ' + resp.status + '）');
    }
    if (!data || data.ok !== true) {
      throw new Error((data && data.error) || ('请求失败（HTTP ' + resp.status + '）'));
    }
    return data.data;
  }

  function post(url, payload) {
    return request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
  }

  createApp({
    setup() {
      const path = ref('');
      const status = ref({ state: 'idle', products: 0, done: 0, total: 0, message: '', error: '' });
      const error = ref('');
      const note = ref('');
      const picking = ref(false);
      const restoring = ref(false);
      const file = ref(null);
      let timer = null;

      const running = computed(() => status.value.state === 'running');
      const percent = computed(() => {
        const s = status.value;
        return s.total ? Math.min(100, Math.round(s.done / s.total * 100)) : 0;
      });

      async function refresh() {
        try {
          status.value = await request('/api/setup/status');
          if (status.value.state === 'running') {
            schedule();
          } else if (status.value.state === 'done') {
            note.value = '导入完成，正在进入系统…';
            setTimeout(() => { location.href = '/index.html'; }, 1500);
          }
        } catch (e) {
          // 服务刚起来时可能还没就绪，下一次轮询再试
        }
      }

      function schedule() {
        clearTimeout(timer);
        timer = setTimeout(refresh, 800);
      }

      async function pick() {
        picking.value = true;
        error.value = '';
        try {
          const data = await post('/api/setup/pick_folder');
          if (data.path) path.value = data.path;
        } catch (e) {
          error.value = '打开选择框失败：' + e.message + '（可以直接粘贴文件夹路径）';
        } finally {
          picking.value = false;
        }
      }

      async function startImport() {
        error.value = '';
        note.value = '';
        try {
          await post('/api/setup/import', { path: path.value });
          status.value = { state: 'running', products: 0, done: 0, total: 0,
                           message: '正在准备…', error: '' };
          schedule();
        } catch (e) {
          error.value = e.message;
        }
      }

      function onFile(event) {
        file.value = (event.target.files || [])[0] || null;
      }

      async function restore() {
        if (!file.value) return;
        if (!confirm('恢复会覆盖当前数据（会先自动备份）。确定继续？')) return;
        restoring.value = true;
        error.value = '';
        note.value = '';
        try {
          const buffer = await file.value.arrayBuffer();
          const resp = await fetch('/api/setup/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: buffer,
          });
          const result = await resp.json();
          if (!result.ok) throw new Error(result.error || '恢复失败');
          note.value = '恢复完成：' + result.products + ' 个产品，正在进入系统…';
          setTimeout(() => { location.href = '/index.html'; }, 1500);
        } catch (e) {
          error.value = '恢复失败：' + e.message;
        } finally {
          restoring.value = false;
        }
      }

      function goIndex() {
        location.href = '/index.html';
      }

      onMounted(refresh);

      return {
        path, status, error, note, picking, restoring, running, percent, file,
        pick, startImport, onFile, restore, goIndex,
      };
    },
  }).mount('#welcomeApp');
})();
