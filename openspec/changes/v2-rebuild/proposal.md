# Proposal

## Why

系统虽然已经做过一次分层，但业务主干仍留在 `工具/`：一次导入要跨三层子进程，进度靠正则匹配中文日志判断；目录、文件名、接口字段中英混杂，一次性迁移脚本和兼容 shim 与在用代码堆在同一层；前端是 6 个全局脚本加内联 `onclick`，新功能只能继续往上堆。十多名同事各自解压独立使用、后续还要接易快报导出，这套结构已经很难低成本维护。

## What Changes

- **BREAKING** 目录与文件英文化：`工具/` → `tools/`、`合同模板/` → `templates/`、`运行环境/` → `runtime/`，入口收敛为 `start.bat` / `stop.bat` / `maintenance.bat`
- **BREAKING** HTTP 接口改为资源化路径、统一响应信封、英文 snake_case 字段，不再使用中文 JSON 键
- 清理：删除 `tests/`（已保留 `tools/docx_diff.py`）、`dist/`、一次性迁移脚本、旧 `web/js` 全局脚本与 `web/vendor`；旧数据与旧模板归档到 `data/_archive/`
- 后端：入口改为 `python -m app`，用 Flask 承载路由与错误处理；`store.py` 拆为 `infra/schema.py` 与 `infra/repositories/*`；`工具/` 里的解析与合并下沉为 `domain/parser.py`、`domain/merge.py`，导入不再跨子进程
- 前端：改为 Vite + Vue 3 单页应用（hash 路由），4 个页面 + 共用组件，构建产物 `web/dist` 随包分发
- 输出：生成的合同从 `web/_生成合同` 迁到 `data/output`，位置可通过设置覆盖
- 入口：程序根目录放一个「采购下单系统」快捷方式，指向无控制台的便携运行时；关闭最后一个页面后服务自动退出，`start.bat` 只保留作排错入口
- 分发：发布包只含程序、模板、快捷方式与便携运行时；升级只替换程序，`data/` 原样保留
- 保留不变：合同模板填充规则、金额与付款判定、搜索行为、易快报下载流程、备份策略

## Capabilities

### New Capabilities

- `portable-app`: 快捷方式入口、启动、自动退出、单实例、首启向导，以及发布包与升级行为
- `http-api`: 接口路径、响应信封、错误语义与字段命名契约
- `catalog`: 产品与供应商检索、图片、供应商档案与合同台账
- `contract-drafting`: 下单表单、金额与付款方式、主合同与信息表生成、输出位置
- `ekb-import`: 易快报批次导入与本地文件夹导入
- `data-safety`: 数据目录、备份、恢复与结构迁移

### Modified Capabilities

无。项目此前没有 OpenSpec 规格。

## Impact

- 代码：`app/` 全部重排；`工具/` 只保留 `build_release.py`、`maintenance.py`、`docx_diff.py`；`web/` 整体替换
- 数据：`purchase.db` 结构保持 v3，不需要数据迁移；`data/media`、`data/backups` 不动
- 依赖：便携运行时新增 Flask、Werkzeug、Jinja2、itsdangerous、MarkupSafe；前端开发期需要 Node 22，同事侧仍只拿构建产物
- 分发：包体积与现在基本持平；同事侧仍是解压即用、各自独立
- 风险：接口字段改名后前后端必须同批切换，过渡期旧页面不可用
