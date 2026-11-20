# Tasks

## 1. 名称归一与合同解析

- [x] 1.1 新增 `app/domain/names.py`，实现 `name_key()`（NFKC、去空白、去书名号、小写）与 `clean_supplier_name()`（按联系人/电话/地址/统一社会/开户/盖章/日期截断，去内部空格）；用全角括号、内部空格、带标签三段样例验证输出符合预期
- [x] 1.2 改写 `app/domain/parser.py` 的乙方提取：首部表格同一单元格优先，其次右侧单元格，再正文前 80 段，最后文件名；取值按标签截断，删除按空格切第一个词的逻辑；用 `优尚（广州）礼品贸易有限公司`、`萌创优品（广东）玩具制品有限公司` 等样例合同验证名称完整
- [x] 1.3 解析时增加甲方归属：首部“购货单位（甲方）”、标签邻近、两家公司全名命中三种方式；无法识别时留空；用含两家名称的合同验证优先取标签邻近的一方
- [x] 1.4 `app/domain/merge.py` 与 `app/infra/store.py` 的供应商匹配、档案保存改为按 `name_key`；对同一份合同连续导入两次，验证供应商数量不增加
- [x] 1.5 用桌面合同目录抽样（至少包含 1 份 `.doc`、1 份附件式订购清单、1 份同时出现两家公司的合同）做只读提取对比，确认乙方不截断、甲方不误判，并把结果记录到变更说明

## 2. 结构 v4 与存储

- [x] 2.1 `app/infra/schema.py` 增加 v4 迁移：`contracts` 加 `party_a`、`party_a_source`、`source_path`；`suppliers`、`supplier_profiles` 加 `name_key`；新增 `supplier_party_terms`、`supplier_merge_log` 与索引；启动本地服务并调用系统状态，确认 `schema_info()` 返回 current=4
- [x] 2.2 迁移中回填 `suppliers.name_key` 与 `supplier_profiles.name_key`，建立唯一索引；验证归一化后同名记录不会触发唯一约束失败
- [x] 2.3 迁移中自动合并归一化后完全相同的供应商（预期 2 组，166 → 164），重挂产品、合同、档案、期限；验证产品数与关系数不变
- [x] 2.4 把 `supplier_contract_terms` 的全部记录迁入 `supplier_party_terms`（`party_a=''`），旧表保留；验证行数一致、页面手工期限仍显示
- [x] 2.5 在 `store.py` 新增 `supplier_contract_stats_by_party()`，按“供应商 + 甲方”输出最近签约、期限、剩余天数、档位、待确认；改造 `contract_expiry_overview()` 与 `list_suppliers_light()`；用一家有两家甲方合同的数据验证输出两行、只有一家时输出一行
- [x] 2.6 在 `store.py` 新增 `merge_suppliers(source, target)`：单事务重挂 `supplier_products`、`contracts`、`historical_order_items`、`supplier_profiles`、`supplier_party_terms`、`product_supplier_names`，写 `supplier_merge_log`；用两个测试供应商验证合并后只剩目标行且关联数量正确

## 3. 历史甲方回填

- [x] 3.1 新增 `tools/backfill_party_a.py`，默认只读：按 `S\d{8}` 匹配桌面合同目录与台账，输出可匹配数、甲方分布、未识别清单、无文件清单；运行前后对比数据库文件哈希，验证没有写入
- [x] 3.2 实现 `--apply`：先备份数据库，再在单事务内写 `party_a`、`party_a_source='content'`、`source_path`；验证写入后 638 份有甲方、56 份为空
- [x] 3.3 验证回填幂等与失败回滚：重复执行 `--apply` 结果不变；人为制造异常时合同甲方字段保持回填前状态
- [x] 3.4 在 `docs/maintenance.md` 补充 dry-run 与 apply 的命令、输出含义、备份位置；按文档实际执行一遍验证命令可用

## 4. 接口

- [x] 4.1 `/api/suppliers` 增加 `parties` 数组（含未确认甲方项），`serializers.py` 输出 snake_case；用 curl 请求验证两家甲方时返回两行、单家时返回一行
- [x] 4.2 播种 `party_a_profiles` 两家公司，新增 `GET /api/party-a` 与 `PUT /api/party-a`；验证读取包含名称、简称、信用代码、联系人、电话、邮箱、地址，修改后再次读取生效
- [x] 4.3 `/api/contracts/terms` 的保存与删除增加 `party_a`，`/api/contracts/expiry` 的 item 增加 `party_a`；验证同一供应商两家甲方的期限互不影响
- [x] 4.4 新增 `GET /api/suppliers/duplicates` 与 `POST /api/suppliers/merge`；验证候选清单包含 10 组短名，合并后供应商数与关联数据正确
- [x] 4.5 更新 `docs/api.md` 的新增接口与字段；按文档示例逐条请求，确认响应结构与文档一致
- [x] 4.6 新增 `GET /api/contracts/sync` 与 `POST /api/contracts/sync`，复用 `services/sync.py`；验证空闲状态返回 idle、重复提交返回 409

## 5. 前端

- [x] 5.1 新增 `web/src/lib/party-a.js`，统一加载甲方目录并记住上次选择；`ContractPage.vue` 删除硬编码常量改用该模块；全局搜索确认页面代码中不再有作为数据源的“广州兴趣岛信息科技有限公司”常量
- [x] 5.2 `OrderPage.vue` 的“已有主合同”提示改为按甲方分行，显示最近签约、合同号、起止日期、剩余天数、待确认；用两家甲方数据验证显示两行，未确认甲方单独提示
- [x] 5.3 下单页增加甲方选择，`order-docs.js` 的购货单位、甲方签署行、主体合同甲方与主合同日期改为入参；分别用两家甲方导出，解压 docx 检查 `document.xml` 中甲方名称与日期正确，且文件名不含甲方简称
- [x] 5.4 实现换供应商 2×2 状态机：空单直接切；有产品未导出每次弹确认；已导出静默清空；刷新恢复不触发。搜索框文本一改、删空失焦或点 × 都走同一规则，取消通过 `:key` 重挂回退；用浏览器验证修改文本、取消、确认和已导出组合
- [x] 5.8 按旧版版式重做下单页：供应商搜索与已选卡片并排，合同摘要按甲方分行、显示整体有效期与待确认；甲方信息块放在汇总卡底部，字段可编辑并失焦保存；用浏览器截图核对
- [x] 5.9 接入数据新鲜度与“立即更新”：显示更新时间、待导入数量、来源目录不可用提示；更新时轮询进度，完成后刷新目录、到期数据和当前供应商
- [x] 5.10 导出 Word 的单价、行小计、合计和结算金额改为整元不带 `.00`、非整元保留两位；用 `docx` 文本检查 `19,300`、`45,140` 与 `38.60`
- [x] 5.5 `ExpiryPage.vue` 增加甲方列、“未确认甲方”筛选、按甲方登记/修改/撤销期限，“续签”携带甲方进入新增主合同页；验证两家甲方期限独立、未确认合同可指定
- [x] 5.6 `SystemPage.vue` 增加甲方信息编辑与供应商去重面板；验证保存后下单页生效、合并前有备份提示、合并后列表只剩目标供应商
- [x] 5.7 运行 `npm run lint` 与 `npm run build`，确认无错误且 `web/dist` 的修改时间晚于 `web/src`

## 6. 集成验收

- [x] 6.1 核对数据完整性：产品 1053、合同 694、供应商 164、历史订单行 962 在产品与供应商合并后关系数不减少；把结果写入变更说明
- [x] 6.2 从桌面合同目录导入一份已收录合同，验证报告显示重复跳过、供应商数与产品数不变
- [x] 6.3 用 `tools/docx_diff.py` 对比新旧订购清单与主合同，确认除甲方名称与主合同日期外无差异
- [x] 6.4 关闭最后一个页面，验证服务在约 10 秒内退出、端口释放；刷新与多标签页不误退
- [x] 6.5 运行 `python tools/build_release.py`，确认发布包包含新前端与 v4 程序且不包含 `data/`、图片与缓存

## Workflow follow-up

- 变更验收通过后归档，并把 5 个能力规格同步到主规格。
- 归档后检查 `openspec/specs/` 中新增的 `party-a` 能力与修改后的 catalog、contract-drafting、ekb-import、data-safety 内容完整。
