# http-api Specification

## Purpose
定义前端与后端之间稳定、可读、可验证的接口契约，使界面重做或新增功能时不需要猜测字段。

## Requirements

### Requirement: 资源化路径

接口路径 SHALL 使用英文名词复数与层级结构，例如 `/api/products`、`/api/contracts`、`/api/imports/ekuaibao`，MUST NOT 使用动词式或含中文的路径。

#### Scenario: 查询产品

- **WHEN** 前端按关键字取产品
- **THEN** 请求 `GET /api/products?q=a4&limit=20`，返回产品数组

#### Scenario: 生成合同

- **WHEN** 前端提交一次下单
- **THEN** 请求 `POST /api/contracts`，而不是 `POST /api/make_contract`

### Requirement: 统一响应信封

所有接口 SHALL 返回 `{"ok": true, "data": ...}` 或 `{"ok": false, "error": {"code": "...", "message": "..."}}` 两种结构之一。

#### Scenario: 成功响应

- **WHEN** 请求正常完成
- **THEN** 响应体包含 `ok: true` 与 `data`

#### Scenario: 失败响应

- **WHEN** 请求参数缺失
- **THEN** 响应体包含 `ok: false`，`error.code` 为稳定的英文标识，`error.message` 为可直接展示的中文提示

### Requirement: 字段命名

JSON 字段 SHALL 使用英文 snake_case；中文只允许出现在数据值中，不得作为键名。

#### Scenario: 供应商对象

- **WHEN** 接口返回供应商
- **THEN** 字段为 `name`、`phone`、`contract_count`，而不是 `供应商`、`电话`

#### Scenario: 业务值保持中文

- **WHEN** 返回供应商名称或产品名称
- **THEN** 值仍是中文原文，不做翻译或转码

### Requirement: HTTP 状态语义

客户端错误 SHALL 返回 4xx，服务端异常 SHALL 返回 5xx，MUST NOT 用 200 包装失败结果。

#### Scenario: 模板缺失

- **WHEN** 生成合同时法务模板文件不存在
- **THEN** 返回 500，`error.code` 为 `template_missing`

#### Scenario: 参数不合法

- **WHEN** 数量传入负数
- **THEN** 返回 400，`error.code` 为 `invalid_argument`

### Requirement: 长任务不阻塞

导入等长任务 SHALL 立即返回任务标识，进度通过状态接口轮询，MUST NOT 让请求线程等待任务结束。

#### Scenario: 启动易快报导入

- **WHEN** 前端提交导入请求
- **THEN** 立即返回批次标识，前端轮询 `GET /api/imports/current` 获取 `phase`、`done`、`total`

#### Scenario: 重复提交

- **WHEN** 已有导入任务在运行时再次提交
- **THEN** 返回 409，`error.code` 为 `import_running`
