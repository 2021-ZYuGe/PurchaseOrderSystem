# Proposal

## Why

下单页目前只按供应商汇总合同，无法区分同一供应商在两家甲方主体下的签约情况；期限取“该供应商所有合同里止日最晚的一份”，会让一家的长期合同掩盖另一家已经到期。与此同时，供应商名称在解析时被按空格截断、入库时没有全半角归一，导致下拉列表出现同一家公司多条记录（实测 166 家中 2 组完全重复、10 组短名），选错供应商就会影响下单与导出。历史合同文件仍完整保存在本机合同目录，具备按正文回填甲方归属的条件。

## What Changes

- 合同台账增加甲方归属：新增 `party_a`、`party_a_source`、`source_path`，导入时从合同首部读取，历史数据从本机合同文件按正文回填。
- 合同期限与到期统计从“按供应商”细化为“按供应商 + 甲方”，下单提示按甲方分行显示，每家一行、各自期限。
- 甲方主体信息改为后端数据源（两家公司），下单页可选择并编辑甲方；《产品订购清单》的购货单位、签署行和“主合同日期”跟随所选甲方。
- 下单页按旧版版式重做供应商区：搜索与已选卡片并排，合同摘要按甲方分行显示最近签约与各自期限，并展示数据更新时间和“立即更新”入口。
- 换供应商时清空已选产品、单价和付款方式：空单直接切换，未导出时每次弹确认，已导出后静默清空；取消保留原内容。
- 乙方名称读取改为首部表格优先，按标签截断而不是按空格切词，并做全半角归一；存量供应商自动合并完全重复的 2 组，短名 10 组与“萌优”由人工确认合并。
- 数据库结构升级到 v4，迁移前自动备份；历史甲方回填提供只读 dry-run 报告和可重复执行的 apply 步骤。
- **BREAKING**：结构升级后旧版程序无法打开 v4 数据库（沿用现有降级保护），回退需恢复备份并使用旧发布包。

## Capabilities

### New Capabilities

- `party-a`: 甲方主体目录、合同甲方归属（自动读取与人工指定）、按甲方分组的合同期限与到期视图。

### Modified Capabilities

- `catalog`: 供应商名称归一化与唯一键、重复供应商合并、供应商列表按甲方返回合同摘要。
- `contract-drafting`: 下单页甲方选择、订购清单内容与主合同日期跟随甲方、换供应商重置规则。
- `ekb-import`: 合同解析时乙方名称首部优先，并在同一流程记录甲方。
- `data-safety`: 结构 v4 迁移、历史甲方回填与供应商合并的备份、预览和回退要求。

## Impact

- 数据库：`contracts` 新增 3 列；`suppliers`、`supplier_profiles` 新增 `name_key`；新增 `supplier_party_terms`、`supplier_merge_log`；迁移版本 v4。
- 接口：`/api/suppliers` 增加 `parties`；新增 `/api/party-a`、`/api/suppliers/duplicates`、`/api/suppliers/merge`；期限接口增加 `party_a`；`/api/contracts/expiry` 按甲方出行。
- 前端：`web/src/pages/OrderPage.vue`、`ContractPage.vue`、`ExpiryPage.vue`、`SystemPage.vue`，新增 `web/src/lib/party-a.js`，调整 `web/src/lib/order-docs.js`。
- 解析与存储：`app/domain/parser.py`、`app/domain/merge.py`、新增 `app/domain/names.py`、`app/infra/schema.py`、`app/infra/store.py`。
- 运维：新增 `tools/backfill_party_a.py`（默认只读），迁移与合并前自动备份到 `data/backups`。
- 不改动：关页自动退出行为、产品/图片数据结构、合同模板填充规则、付款阈值规则。
- 依赖：不新增第三方依赖。
