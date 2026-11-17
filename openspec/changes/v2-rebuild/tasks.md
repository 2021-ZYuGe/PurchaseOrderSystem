# Tasks

## 1. 冻结与清理

- [x] 1.1 给当前提交打 `v1` tag，并导出发布包到项目外保存；验证：`git tag -l` 能看到 `v1`，项目外存在可运行的 zip
- [x] 1.2 删除 `tests/`，保留 `tools/docx_diff.py`；验证：`tests/` 不存在，`runtime\python.exe tools/docx_diff.py --snapshot <模板>` 有输出
- [x] 1.3 旧版合同模板归档到 `data/_archive/templates/`；验证：`合同模板/` 下只剩 3 个现行模板
- [x] 1.4 删除 `dist/`、所有 `__pycache__`、空的 `web/_生成合同`；验证：目录不存在，服务仍能启动
- [x] 1.5 归档 `data/` 下 9 个旧 JSON 到 `data/_archive/`，归档前确认 `schema_meta` 已有 `legacy_import_completed` 与 `history_source_signature`；验证：产品 1053、合同 671、历史 962 三个计数不变
- [x] 1.6 删除 13 个一次性脚本与 4 个遗留入口（详见 proposal 的清理清单）；验证：`tools/` 只剩计划内文件，`start.bat` 仍能启动
- [x] 1.7 把 `web/图片/` 打包成 `data/_archive/legacy-media.zip` 后删除原目录；验证：`data/media` 仍是 536 张，页面图片正常显示
- [x] 1.8 更新 `.gitignore`：去掉 tests 规则，加入 `web/dist` 例外与 `data/_archive/`；验证：`git status --ignored` 中没有意外文件

## 2. 目录与入口英文化

- [x] 2.1 用 `git mv` 把 `工具/` → `tools/`、`合同模板/` → `templates/`、`运行环境/` → `runtime/`；验证：根目录不再有中文目录，`git log --follow` 仍能追到历史
- [x] 2.2 更新 `config.py` 路径常量、三个 bat、构建脚本中的中文路径引用；验证：启动、导入、生成合同三条链路都通
- [x] 2.3 根入口收敛为 `start.bat` / `stop.bat` / `maintenance.bat`，删除其余 bat；验证：三个脚本各自可执行，无残留引用
- [x] 2.4 改为 `python -m app` 启动，新增 `app/__main__.py`，删除所有 `sys.path` 注入与 `tools/sqlite_store.py` 兼容层；验证：`runtime\python.exe -m app` 能起服务
- [x] 2.5 新增 `pyproject.toml`（ruff/格式配置）与 `.editorconfig`；验证：`runtime\python.exe -m compileall app` 通过
- [x] 2.6 实现 `tools/make_shortcut.py`，生成根目录的「采购下单系统」快捷方式（`pythonw -m app`、工作目录、图标、相对路径）；验证：双击无控制台窗口、图标正确，文件夹改名后仍能启动

## 3. HTTP 层与后端骨架

- [x] 3.1 在便携运行时安装 Flask、Werkzeug、Jinja2、itsdangerous、MarkupSafe，并写入 `requirements.txt`；验证：`runtime\python.exe -c "import flask, werkzeug, jinja2, itsdangerous, markupsafe"`
- [x] 3.2 `api/server.py` 只保留生命周期：单实例复用、端口探测、空闲退出，不再结束其它目录的实例；验证：同目录重复启动复用，另一目录的实例不被杀
- [x] 3.3 实现 `api/responses.py` 与 `api/router.py`：统一信封、错误码、HTTP 状态语义；验证：未知路径返回 404 且 `ok=false`
- [x] 3.4 按资源拆分 `api/handlers/*`，服务通过参数传入，handler 不写 SQL；验证：每个 handler 不超过 120 行
- [x] 3.5 改用标准 `logging` 写 `data/logs/app.log` 按天滚动；验证：运行后生成当天日志，`data/_运行日志.txt` 不再出现
- [x] 3.6 实现页面心跳与空闲退出：SSE `/api/events/alive`、`sendBeacon` 到 `/api/events/bye`、10 秒宽限、按页签计数；验证：关最后一个标签页 15 秒内进程退出，刷新不退，两个标签页关一个不退

## 4. 领域层下沉

- [ ] 4.1 用 v1 生成 3 份基线文档（主合同、信息表、订购清单）存入 `data/_archive/baseline/`；验证：3 份 docx 都能用 Word 打开
- [x] 4.2 抽出 `domain/parser.py`（金额大写、签约日期、表格识别、单元格图片），按函数搬迁不改逻辑；验证：同一批 10 份合同解析结果与旧脚本逐字段一致
- [x] 4.3 抽出 `domain/merge.py`（产品/供应商合并、合同台账、收录索引）；验证：合并同一批次后 products、suppliers、contracts 计数与旧脚本一致
- [x] 4.4 `import_service` 改为进程内调用 parser 与 merge，进度用回调上报；验证：导入 10 份合同，进度单调递增且任务管理器无子进程
- [x] 4.5 用 `docx_diff.py` 比对 v1 与 v2 生成的 3 份文档，确认零差异后再删除旧脚本；验证：输出"内容一致"
- [ ] 4.6 `contract_doc.py` 内部标识符英文化（模板占位符不动），逻辑零改动；验证：diff 只包含改名，`docx_diff` 仍然一致

## 5. 数据层拆分

- [ ] 5.1 抽出 `infra/schema.py`（SCHEMA + MIGRATIONS）；验证：全新库初始化后 `schema_version=3`
- [x] 5.2 实现 `repositories/catalog.py`（搜索、产品详情、目录元信息）；验证：同一组 20 个关键字，搜索结果与 v1 逐条一致
- [x] 5.3 实现 `repositories/suppliers.py`（列表、档案、合同期限）；验证：供应商 165 家、档案 93 条读取一致
- [x] 5.4 实现 `repositories/contracts.py`（台账、到期分桶、待导入扫描）；验证：到期分桶结果与 v1 一致
- [x] 5.5 删除 `_migrate_legacy`、`_replace_history_sources` 及旧 JSON 读取代码；验证：启动无报错，历史下单 962 条仍在
- [x] 5.6 对现有库执行 `PRAGMA integrity_check` 并逐表比对计数；验证：`ok`，且与改造前一致

## 6. 接口契约与前端

- [x] 6.1 按 `http-api` 规格实现全部接口，字段全部英文 snake_case；验证：每个接口用 curl 跑通，响应符合统一信封
- [x] 6.2 初始化 `web/` 的 Vite + Vue 3 工程（router、api client、样式变量）；验证：`npm run build` 产出 `web/dist`
- [x] 6.3 下单页与产品搜索组件；验证：选供应商、加 2 个产品，合计与手算一致
- [x] 6.4 合同页（付款方式、乙方信息、信息表）；验证：低于阈值时预付选项置灰并给出原因
- [x] 6.5 导入页（预览、进度、历史）与首启向导；验证：预览新增数与实际入库数一致
- [x] 6.6 删除 `web/js`、`web/vendor` 与旧 html，只留 `dist` 与源码；验证：`dist` 独立运行，控制台无 404
- [ ] 6.7 前端 lint 与格式化配置；验证：`npm run lint` 无错误

## 7. 输出、打包与文档

- [x] 7.1 生成文档改写到 `data/output`，由后端受控路由提供下载；验证：文件落在 `data/output`，链接可下载
- [x] 7.2 支持 `settings.json` 覆盖 `output_dir`；验证：改到临时目录后新文件落在那，旧文件不迁移
- [x] 7.3 重写 `tools/build_release.py`（英文路径、清单校验、依赖冒烟、dist 新鲜度、打包时生成快捷方式）；验证：包内包含 runtime、`.lnk` 与 `app.ico`，不含 `data/`、`web/src`、`__pycache__`
- [x] 7.4 写 `docs/`：README、使用说明、维护说明（升级、备份、合同比对）；验证：新人照文档能独立跑起来
- [x] 7.5 `maintenance.bat` 提供停止、清缓存、看日志、比对合同、重建快捷方式五项；验证：五项都能执行并给出输出

## 8. 集成验收

- [x] 8.1 功能清单逐项走查：快捷方式启动、关页退出、搜索、下单、付款、生成、档案、到期、导入、备份；验证：全部通过并留有记录
- [x] 8.2 本机两套目录模拟：A 目录全新解压使用，B 目录从 v1 覆盖升级；验证：B 数据零丢失，A 首启向导可用
- [x] 8.3 本机用便携运行时启动发布包，确认不依赖系统 Python 与 Node；验证：`start.bat` 正常起服务（多机验证在开发完成后单独进行）
- [ ] 8.4 合并 `rewrite` 分支并打 `v2` tag；验证：主分支可运行，v1 发布包仍可回退

## Workflow follow-up

- 归档本变更：`openspec archive v2-rebuild`
- 归档后确认 `openspec/specs/` 下生成 6 个能力规格
