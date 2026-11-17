# data-safety Specification

## Purpose
保证每台机器上的数据可备份、可恢复、可升级，不会因为替换程序或换电脑而丢失。

## Requirements

### Requirement: 数据位置

所有用户数据 SHALL 位于 `data/`，程序目录 MUST NOT 写入业务数据、日志或生成文档。

#### Scenario: 重装程序

- **WHEN** 删除程序目录但保留 `data/`
- **THEN** 重新解压后数据完整可用，产品与图片数量不变

#### Scenario: 检查写入位置

- **WHEN** 运行一天后检查程序目录
- **THEN** 没有新增 `.db`、日志或生成的 docx

### Requirement: 每日备份

每天首次启动 SHALL 自动备份数据库，保留最近 7 份，超出部分按时间淘汰。

#### Scenario: 连续多日启动

- **WHEN** 连续 10 天每天启动一次
- **THEN** `data/backups` 中只保留最近 7 份自动备份

#### Scenario: 手动备份

- **WHEN** 在系统状态里点击立即备份
- **THEN** 生成一份带时间戳的备份，不参与自动淘汰

### Requirement: 恢复校验

恢复数据库或数据包前 SHALL 校验 sqlite 完整性与结构版本；结构版本高于当前程序时 MUST 拒绝并提示升级。

#### Scenario: 用新备份恢复旧程序

- **WHEN** 旧程序尝试恢复来自更高结构版本的备份
- **THEN** 拒绝恢复，提示先升级程序

#### Scenario: 正常恢复

- **WHEN** 用同版本的备份恢复
- **THEN** 先自动备份当前库，再覆盖，恢复后产品与图片数量与备份一致

### Requirement: 结构迁移

数据库结构变更 SHALL 通过 `schema_migrations` 逐版本执行，迁移前 SHALL 自动整库备份。

#### Scenario: 升级结构

- **WHEN** 程序从结构 v3 升到 v4
- **THEN** 先产生 `before_migration_v4` 备份，再执行迁移，失败时保留原库

#### Scenario: 降级保护

- **WHEN** 用旧程序打开更新结构的数据
- **THEN** 拒绝启动并提示使用新版程序，不写入任何表

### Requirement: 数据包导出与恢复

导出 SHALL 生成包含数据库与图片的 zip；恢复数据包 SHALL 同时还原数据库与图片。

#### Scenario: 换电脑

- **WHEN** 在旧机器导出数据包，在新机器恢复
- **THEN** 产品、供应商、档案、合同台账与图片数量完全一致

### Requirement: 日志位置

运行日志 SHALL 写入 `data/logs/` 并按天滚动，MUST NOT 写进程序目录。

#### Scenario: 排查问题

- **WHEN** 需要排查一次导入失败
- **THEN** 能在 `data/logs/` 找到当天日志与批次报告
