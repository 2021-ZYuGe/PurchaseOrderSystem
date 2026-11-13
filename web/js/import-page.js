// 导入合同页：易快报批次 / 本地文件夹
// Vue 全局版 + 经典脚本，接口都在 /api/import/*
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
      const tab = ref('ekb');
      const url = ref('');
      const folder = ref('');
      const opts = ref({
        template: '合同审批流程',
        keyword: '合同',
        since: '',
        scope: 'all',
        limit: 0,
        include_duplicates: false,
      });
      const preview = ref(null);
      const checking = ref(false);
      const picking = ref(false);
      const status = ref({ state: 'idle', phase: '', message: '', error: '', done: 0, total: 0, result: null });
      const history = ref([]);
      const error = ref('');
      const showProgress = ref(false);
      let timer = null;

      const running = computed(() => status.value.state === 'running');
      const percent = computed(() => {
        const s = status.value;
        return s.total ? Math.min(100, Math.round(s.done / s.total * 100)) : 0;
      });
      const phaseLabel = computed(() => ({
        listing: '连接并读取单据',
        downloading: '下载附件',
        importing: '解析入库',
      }[status.value.phase] || (running.value ? '处理中' : '已完成')));

      async function loadHistory() {
        try {
          const data = await request('/api/import/history');
          history.value = data.items || [];
        } catch (e) { /* 忽略 */ }
      }

      function schedule() {
        clearTimeout(timer);
        timer = setTimeout(poll, 1000);
      }

      async function poll() {
        try {
          status.value = await request('/api/import/status');
        } catch (e) {
          schedule();
          return;
        }
        if (status.value.state === 'running') {
          showProgress.value = true;
          schedule();
        } else {
          loadHistory();
        }
      }

      async function previewEkb() {
        checking.value = true;
        error.value = '';
        preview.value = null;
        try {
          preview.value = await post('/api/import/ekb/preview', Object.assign({ url: url.value }, opts.value));
        } catch (e) {
          error.value = e.message;
        } finally {
          checking.value = false;
        }
      }

      async function startEkb() {
        if (!preview.value) return;
        if (preview.value.new === 0 && !opts.value.include_duplicates) {
          error.value = '这批单据都已导入过；确实要重新下载，请勾选「包含重复单据」。';
          return;
        }
        error.value = '';
        try {
          await post('/api/import/ekb/start', Object.assign({ url: url.value }, opts.value));
          status.value = { state: 'running', phase: 'listing', message: '正在连接易快报…',
                           done: 0, total: 0, result: null, error: '' };
          showProgress.value = true;
          schedule();
        } catch (e) {
          error.value = e.message;
        }
      }

      async function pickFolder() {
        picking.value = true;
        error.value = '';
        try {
          const data = await post('/api/setup/pick_folder');
          if (data.path) folder.value = data.path;
        } catch (e) {
          error.value = '打开选择框失败：' + e.message + '（可以直接粘贴路径）';
        } finally {
          picking.value = false;
        }
      }

      async function startFolder() {
        error.value = '';
        try {
          await post('/api/import/folder', { path: folder.value });
          status.value = { state: 'running', phase: 'importing', message: '正在解析入库…',
                           done: 0, total: 0, result: null, error: '' };
          showProgress.value = true;
          schedule();
        } catch (e) {
          error.value = e.message;
        }
      }

      function reset() {
        clearTimeout(timer);
        preview.value = null;
        error.value = '';
        showProgress.value = false;
        status.value = { state: 'idle', phase: '', message: '', error: '', done: 0, total: 0, result: null };
      }

      onMounted(async () => {
        loadHistory();
        await poll();
      });

      return {
        tab, url, folder, opts, preview, checking, picking, status, history, error,
        showProgress, running, percent, phaseLabel, previewEkb, startEkb, pickFolder,
        startFolder, reset,
      };
    },
  }).mount('#importApp');
})();
