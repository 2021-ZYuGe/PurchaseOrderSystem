# 维护说明

## 升级

1. 把新版本解压到一个新文件夹（不要直接覆盖旧文件夹）。
2. 把旧文件夹里的 `data/` 整个复制到新文件夹。
3. 双击新文件夹的 `start.bat`，数据库结构会自动升级。
4. 确认产品、图片、备份都正常后，再删除旧文件夹。

`data/` 是唯一的用户数据目录，升级只替换程序。

## 备份与恢复

- 每天首次启动会自动备份数据库到 `data/backups/`，保留最近 7 份。
- 手工备份：系统状态页「立即备份」；升级前建议手动备份一次。
- 换电脑：旧机器「系统状态 → 导出数据包」，新机器首启向导里选这个 zip 恢复。
- 恢复前会校验 sqlite 完整性与结构版本；来自更高版本的备份会被拒绝。

## 历史甲方回填（结构 v4）

合同文件默认在 `C:\Users\PC\Desktop\合同下载`，按文件名里的 `S\d{8}` 与台账单号匹配。

```bat
rem 只读预览：不写数据库
runtime\python.exe tools\backfill_party_a.py

rem 确认后执行：先备份，再在事务里写入
runtime\python.exe tools\backfill_party_a.py --apply

rem 合同放在别的目录
runtime\python.exe tools\backfill_party_a.py --dir "D:\合同下载"
```

预览会输出合同总数、匹配到文件的数量、识别成功/未识别/无文件的数量、两家甲方分布和前 15 份未识别样例。
执行前自动备份到 `data/backups/*_before_party_a_backfill.db`；脚本可重复执行，已回填的合同不会重复写。
未识别的合同保持“未确认甲方”，在合同倒计时页筛出来逐条指定即可。

## 改合同逻辑后怎么验证

不要只看页面。用同一份输入分别生成旧版和新版合同，逐段比对：

```bat
runtime\python.exe tools\docx_diff.py old.docx new.docx
```

内容一致返回 0；有差异会逐行打印并返回 1。也可以运行 `maintenance.bat`，
选「比对两份合同」，按提示输入两个文件路径。

## 日志

运行日志：`data/logs/app.log`，按天滚动，保留 14 天。
合并日志：`data/logs/merge.log`。
导入批次：`data/imports/<批次号>/`，含 `batch.json` 与下载记录。

## 常用命令

```bat
start.bat                 启动（日常用快捷方式）
stop.bat                  停止服务
maintenance.bat           停止 / 清缓存 / 看日志 / 重建快捷方式 / 比对合同
python tools\build_release.py   构建发布包
```

## 发布包

发布包只包含程序、模板、快捷方式与便携运行时，不含 `data/`、源码、缓存。
构建脚本会校验包内清单，缺少 `runtime`、`templates` 或混入用户数据都会失败。

## 数据安全

- 不要把 `data/purchase.db` 放进 OneDrive、坚果云等同步目录：SQLite 会锁库，冲突副本可能损坏数据。
- 要同步只同步 `data/output/`（生成好的合同）和 `data/backups/`。
- 删除程序目录前先确认 `data/` 已备份。
