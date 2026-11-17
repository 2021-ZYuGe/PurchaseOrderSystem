<script setup>
import { amountCents, formatCents, mediaUrl } from '../lib/format'

defineProps({
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['update', 'remove', 'cycle', 'preview'])

function update(item, field, value) {
  emit('update', { id: item.id, field, value })
}

function amountText(item) {
  const cents = amountCents(item.unitPrice, item.qty)
  return cents ? formatCents(cents) : '—'
}

function onImageError(event) {
  event.target.style.visibility = 'hidden'
}
</script>

<template>
  <div class="table-scroll">
    <table class="data-table order-table">
      <thead>
        <tr>
          <th style="width: 60px">图片</th>
          <th>产品名称</th>
          <th style="width: 180px">规格</th>
          <th style="width: 110px">单价(元)</th>
          <th style="width: 90px">数量</th>
          <th style="width: 110px">总价(元)</th>
          <th style="width: 190px">备注</th>
          <th style="width: 44px"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id">
          <td>
            <div class="thumb-wrap">
              <button
                v-if="item.image"
                type="button"
                class="thumb-btn"
                title="查看大图"
                @click="emit('preview', mediaUrl(item.image))"
              >
                <img :src="mediaUrl(item.image)" alt="产品图" @error="onImageError" />
              </button>
              <span v-else class="thumb-empty">无图</span>
              <button
                v-if="(item.images || []).length > 1"
                type="button"
                class="img-switch"
                :title="'切换图片（共 ' + item.images.length + ' 张）'"
                @click="emit('cycle', item.id)"
              >
                ⇄
              </button>
            </div>
          </td>
          <td>
            <b>{{ item.name }}</b>
            <div v-if="item.historyPrices && item.historyPrices.length" class="hint">
              历史价: {{ item.historyPrices.slice(0, 3).map((p) => '¥' + p).join(' / ') }}
            </div>
            <div v-if="(item.images || []).length > 1" class="hint">
              共 {{ item.images.length }} 张备选图，点图片右下角 ⇄ 切换
            </div>
          </td>
          <td class="cell-spec">{{ item.spec || '—' }}</td>
          <td>
            <input
              class="input-num"
              type="number"
              min="0"
              step="0.01"
              :value="item.unitPrice"
              placeholder="0.00"
              @input="update(item, 'unitPrice', $event.target.value)"
            />
          </td>
          <td>
            <input
              class="input-num input-qty"
              type="number"
              min="0"
              step="1"
              :value="item.qty"
              placeholder="0"
              @input="update(item, 'qty', $event.target.value)"
            />
          </td>
          <td class="cell-amount">{{ amountText(item) }}</td>
          <td>
            <input
              class="input-text"
              type="text"
              :value="item.remark"
              placeholder="以上价格含13%专票+运费"
              @input="update(item, 'remark', $event.target.value)"
            />
          </td>
          <td>
            <button type="button" class="btn-icon" title="移除" @click="emit('remove', item.id)">
              ✕
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
