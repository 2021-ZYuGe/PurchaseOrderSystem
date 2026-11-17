# HTTP API

前端只通过本文件列出的接口取数。统一约定：

- 成功：`{"ok": true, "data": ...}`
- 失败：`{"ok": false, "error": {"code": "...", "message": "..."}}`
- 字段一律英文 snake_case；中文只出现在值里（供应商名、产品名、备注）。
- 错误码：`invalid_argument`、`not_found`、`conflict`、`auth_expired`、`import_running`、`template_missing`、`internal`。

## 目录与搜索

### GET `/api/catalog/meta`
```json
{"products": 1053, "suppliers": 165, "with_image": 515,
 "updated": "2026-11-11 10:00:10", "revision": 6}
```

### GET `/api/products?q=&supplier=&limit=20`
```json
{"items": [{
  "id": "P0229", "name": "证书", "spec": "尺寸：A4 材质：白卡纸",
  "image": "证书_78a3.png", "images": ["证书_78a3.png", "证书_02.png"],
  "suppliers": ["新胜", "新胜（福州）彩印有限公司"],
  "prices": [0.85, 0.9], "categories": ["印刷"], "aliases": ["奖状"],
  "order_count": 12
}]}
```
图片地址用 `/media/<文件名>`。

### GET `/api/suppliers?q=`
```json
{"items": [{
  "id": "S0031", "name": "新胜（福州）彩印有限公司", "phone": "138...",
  "latest_sign_date": "2026-08-01", "main_contract_date": "2026-08-01",
  "latest_contract_no": "S26014483", "contract_count": 12,
  "history_contract_count": 9, "product_ids": ["P0229", "P0301"]
}]}
```

## 供应商档案

### GET `/api/suppliers/archive?name=`
不传 `name` 返回全部。
```json
{"profiles": [{
  "name": "新胜（福州）彩印有限公司", "credit_code": "9135...",
  "contact": "张三", "tel": "138...", "email": "", "wechat": "",
  "addr": "", "legal": "", "bank_name": "", "bank_account": "",
  "bank_open": "", "last_sign": "2026-08-01", "source": "合同"
}], "party_a": {"广州兴趣岛信息科技有限公司": {"name": "...", "credit_code": "..."}}}
```

### POST `/api/suppliers/archive`
请求体同上单条 profile。返回 `{"saved": true}`。

## 合同期限与生成

### GET `/api/contracts/expiry`
```json
{"today": "2026-11-17", "total": 165,
 "counts": {"expired": 3, "d3": 1},
 "buckets": [{"key": "expired", "label": "已过期", "count": 3}],
 "items": [{
   "supplier": "新胜", "end_date": "2026-12-01", "start_date": "2025-12-01",
   "days_left": 14, "bucket": "d30", "bucket_label": "1 个月内",
   "contract_no": "S26014483", "contract_file": "S26014483/合同.docx",
   "source": "解析", "note": "", "pending": false,
   "last_sign_date": "2025-11-20", "contract_count": 12}]}
```

### POST `/api/contracts/terms`
请求 `{"supplier": "...", "start_date": "2026-01-01", "end_date": "2026-12-31", "note": ""}`
返回 `{"term": {...}, "overview": {同上}}`。

### DELETE `/api/contracts/terms?supplier=新胜`
返回 `{"overview": {同上}}`。

### GET `/api/contracts/status`
```json
{"freshness": {"data_updated_at": "", "last_import": "", "contract_records": 671,
  "imported_files": 700, "last_sign_date": "", "last_main_contract_date": ""},
 "pending": {"checked_dirs": [], "missing_dirs": [], "pending_count": 0,
  "newest_file": "", "newest_date": "", "samples": [], "checked_at": ""}}
```

### GET `/api/contracts/search?q=S26006440&limit=50`
按供应商、合同号、文件名模糊搜索合同台账；多个关键词用空格分隔，按 AND 匹配。
`limit` 默认 50，最大 100。
```json
{"query": "S26006440", "items": [{"supplier": "广州市宝优科技有限公司",
  "contract_no": "S26006440", "filename": "S26006440_..._采购合同.doc",
  "sign_date": "2026-05-26", "main_date": "2026-05-26",
  "start_date": "2026-05-26", "end_date": "2027-05-25"}]}
```

### POST `/api/contracts`
请求体（字段与旧页面 collect 一致）：
```json
{"contract_type": "batch", "remember": true,
 "party_a": {"name": "", "credit_code": "", "contact": "", "tel": "", "email": "", "addr": ""},
 "party_b": {"name": "", "credit_code": "", "contact": "", "tel": "", "email": "",
             "wechat": "", "addr": "", "bank_name": "", "bank_account": "", "bank_open": ""},
 "sign": {"date": "2026-11-17", "years": "1", "place": "广州市天河区"},
 "terms": {"tax_rate": "13", "invoice_type": "专票", "invoice_days": "7",
           "pay_days": "30", "delivery_days": "7", "reconcile_days": "7",
           "invalid_order_pct": "10", "delivery_addr": "", "order_amount": "1000",
           "pay_mode": "full"}}
```
返回 `{"name": "...", "path": "...", "url": "/output/...", "todo": []}`。
`contract_type`：`batch` 批采、`dropship` 一件代发、`simple` 单次简易版。

### POST `/api/contracts/info-sheet`
请求 `{"party_b": {...}}`，返回 `{"name": "...", "path": "...", "url": "/output/..."}`。

## 导入

### POST `/api/imports/ekuaibao/preview`
请求 `{"url": "...", "template": "合同审批流程", "since": "2026-10-01",
        "scope": "all|active|done|paid", "limit": 0, "keyword": "合同", "delay": 1.0}`
返回 `{"who": "", "total_bills": 120, "matching": 15, "new": 12, "duplicates": 3,
        "samples": [{"flow_id": "", "code": "S26014483", "title": "", "state": "",
                     "submit": "2026-11-01", "is_new": true}],
        "duplicate_codes": [], "template": "", "since": "", "scope": "all"}`

### POST `/api/imports/ekuaibao`
同一请求体，立即返回 `{"batch": "20261117_143000"}`；进度用 current 接口。
同一时间只允许一个任务，冲突返回 409 `import_running`。

### POST `/api/imports/folder`
请求 `{"path": "D:/合同下载"}`，返回 `{"batch": "..."}`。

### GET `/api/imports/current`
```json
{"state": "idle|running|done|error", "phase": "listing|downloading|importing",
 "message": "", "error": "", "done": 3, "total": 10, "batch": "",
 "started": "14:30:00", "finished": "", "products": 1053,
 "result": {"id": "", "source": "", "stats": {}, "import": {}, "files": 0}}
```

### GET `/api/imports/history?limit=10`
`{"items": [{"id": "", "source": "ekuaibao|folder", "created": "", "status": "", "message": "", "stats": {}}]}`

## 首启向导

### GET `/api/setup/status`
`{"state": "idle|running|done|error", "message": "", "error": "", "done": 0, "total": 0,
  "started": "", "finished": "", "products": 0, "need_setup": true}`

### POST `/api/setup/import` `{"path": "D:/合同"}`
### POST `/api/setup/pick-folder` → `{"path": "D:/合同"}`（取消返回空串）
### POST `/api/setup/restore`
请求体为 sqlite 或 zip 的原始字节（`application/octet-stream`），
返回 `{"products": 1053, "media": 536}`。

## 系统状态

### GET `/api/system/info`
```json
{"version": "2026-11-13", "data_dir": "...",
 "db": {"size": 2068480, "updated_at": "2026-11-17 10:00"},
 "media_count": 536,
 "counts": {"products": 1053, "suppliers": 165, "with_image": 515},
 "schema": {"version": 3, "migrations": []},
 "backups": {"count": 7, "latest": "purchase-...db", "latest_at": ""}}
```

### GET `/api/system/backups` → `{"items": [{"name": "", "size": 0, "at": ""}]}`
### POST `/api/system/backup` → `{"name": "", "size": 0}`
### GET `/api/system/backup/download` → sqlite 文件下载
### GET `/api/system/export` → 数据包 zip 下载

## 静态与运行时

- 产品图片：`/media/<文件名>`
- 生成的合同：`/output/<文件名>`
- 页面在线心跳（自动退出用）：
  - `GET /__alive?id=<随机页签 id>`（SSE 长连接）
  - 页面 `pagehide` 时 `navigator.sendBeacon('/__bye?id=<id>')`
  - 关闭最后一个页签后 10 秒，服务自动退出
