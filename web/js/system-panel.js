// 系统状态面板（Vue 3 组件）
// 新功能的写法示例：Vue 全局版 + 经典脚本挂载，不需要 Node 构建链。
// 依赖 app-core.js 提供的 fetchJSON；组件只会挂到 #systemPanel。
(function () {
  if (!window.Vue) return;                 // Vue 没加载成功时静默跳过，不影响主流程
  const { createApp, ref, computed } = Vue;

  function fmtSize(bytes) {
    const n = Number(bytes || 0);
    if (!n) return '—';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }

  createApp({
    setup() {
      const open = ref(false);
      const loading = ref(false);
      const error = ref('');
      const info = ref(null);
      const note = ref('');

      async function load() {
        loading.value = true;
        error.value = '';
        try {
          info.value = await fetchJSON('/api/system/info');
        } catch (e) {
          error.value = e.message || String(e);
        } finally {
          loading.value = false;
        }
      }

      function show() {
        open.value = true;
        load();
      }

      function close() {
        open.value = false;
      }

      async function backupNow() {
        note.value = '';
        try {
          const data = await fetchJSON('/api/backup/now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          });
          note.value = data.name ? ('已备份：' + data.name) : '当前还没有数据库，无需备份';
          await load();
        } catch (e) {
          note.value = '备份失败：' + (e.message || e);
        }
      }

      function downloadDb() {
        location.href = '/api/backup/download';
      }

      const rows = computed(() => {
        const d = info.value;
        if (!d) return [];
        return [
          { k: '程序版本', v: d.version + '（数据 v' + d.schema.current + '）' },
          { k: '产品 / 供应商', v: d.counts.products + ' 个 / ' + d.counts.suppliers + ' 家' },
          { k: '图片', v: d.counts.with_image + ' 个产品有图（共 ' + d.media_count + ' 张）' },
          { k: '数据库', v: fmtSize(d.db.size) + (d.db.updated_at ? ' · ' + d.db.updated_at : '') },
          { k: '数据目录', v: d.data_dir, wide: true },
          { k: '备份', v: d.backups.count ? (d.backups.count + ' 份 · 最近 ' + d.backups.latest_at) : '暂无' },
        ];
      });

      return { open, loading, error, info, rows, note, show, close, load,
               backupNow, downloadDb };
    },
    template: `
      <a class="btn-expiry" href="javascript:;" @click="show">系统状态</a>
      <div class="exp-modal show" v-if="open" @click.self="close">
        <div class="exp-panel sys-panel">
          <div class="exp-head">
            <div>
              <div class="exp-title">系统状态</div>
              <div class="exp-sub">本机版本、数据位置与备份情况</div>
            </div>
            <button class="exp-close" type="button" @click="close" title="关闭">×</button>
          </div>
          <div class="sys-body">
            <div v-if="loading" class="sys-empty">正在读取…</div>
            <div v-else-if="error" class="sys-empty sys-error">读取失败：{{ error }}</div>
            <template v-else>
              <div class="sys-row" v-for="row in rows" :key="row.k">
                <span class="sys-k">{{ row.k }}</span>
                <b class="sys-v" :class="{ 'sys-wide': row.wide }">{{ row.v }}</b>
              </div>
            </template>
          </div>
          <div class="sys-note" v-if="note">{{ note }}</div>
          <div class="sys-foot">
            <button type="button" class="sys-btn" @click="backupNow">立即备份</button>
            <button type="button" class="sys-btn" @click="downloadDb">下载数据库</button>
            <span class="sys-spacer"></span>
            <button type="button" class="sys-btn" @click="load" :disabled="loading">
              {{ loading ? '读取中…' : '刷新' }}
            </button>
            <button type="button" class="sys-btn primary" @click="close">关闭</button>
          </div>
        </div>
      </div>
    `
  }).mount('#systemPanel');
})();
