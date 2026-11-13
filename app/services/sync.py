# -*- coding: utf-8 -*-
"""一键更新：把扫描到的新合同交给 合并新合同.py 解析入库。

P1 仍然走子进程（和原来完全一致），P5 会改成服务内调用 + 进度上报。
"""
import os
import subprocess
import sys
import threading
import time

import app.config as config
from app.infra import store as sqlite_store
from app.infra.logging import log


SYNC_LOCK = threading.Lock()
SYNC_STATE = {"state": "idle", "total": 0, "started": "", "finished": "", "message": ""}
SYNC_PY = os.path.join(config.ROOT, '运行环境', 'python.exe')
if not os.path.exists(SYNC_PY):
    SYNC_PY = sys.executable


def _sync_status():
    with SYNC_LOCK:
        return dict(SYNC_STATE)


def _set_sync(**kw):
    with SYNC_LOCK:
        SYNC_STATE.update(kw)


def _start_sync():
    items = sqlite_store.scan_pending_contracts().get("路径清单") or []
    if not items:
        return {"ok": False, "error": "没有检测到需要导入的新合同"}
    with SYNC_LOCK:
        if SYNC_STATE.get("state") == "running":
            return {"ok": False, "error": "正在更新中，请稍候"}
        SYNC_STATE.update({
            "state": "running", "total": len(items), "started": time.strftime("%H:%M:%S"),
            "finished": "", "message": "正在解析 %d 份合同…" % len(items),
        })
    threading.Thread(target=_sync_worker, args=(items,), daemon=True).start()
    return {"ok": True, "total": len(items)}


def _sync_worker(items):
    groups = {}
    for item in items:
        path = item.get("路径") or ""
        if not path:
            continue
        root = item.get("根") or os.path.dirname(path)
        groups.setdefault(root, []).append(path)
    log("一键更新开始：%d 份合同 / %d 个来源目录" % (len(items), len(groups)))

    messages, ok_all = [], True
    for root, paths in groups.items():
        listfile = str(config.DATA_DIR / ('_待导入清单_%d.txt' % int(time.time() * 1000)))
        try:
            with open(listfile, 'w', encoding='utf-8') as f:
                f.write("\n".join(paths))
            cmd = [SYNC_PY, str(config.MERGE_SCRIPT),
                   '--files', listfile, '--yes', root]
            result = subprocess.run(
                cmd, cwd=config.ROOT, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800,
            )
            text = result.stdout.decode('gbk', errors='replace')
            if "合并完成" in text:
                messages.append("导入 %d 份成功" % len(paths))
            else:
                ok_all = False
                tail = " / ".join([ln.strip() for ln in text.strip().splitlines() if ln.strip()][-2:])
                messages.append("导入失败：%s" % (tail or "未知错误"))
                log("一键更新失败（%s）：%s" % (root, tail))
        except Exception as e:
            ok_all = False
            messages.append("导入异常：%s" % e)
            log("一键更新异常：%r" % (e,))
        finally:
            try:
                if os.path.exists(listfile):
                    os.remove(listfile)
            except OSError:
                pass

    sqlite_store.clear_pending_cache()
    try:
        sqlite_store.export_data_js()
    except Exception as e:
        log("一键更新后重建缓存失败：%r" % (e,))
    message = "；".join(messages)[:300]
    _set_sync(state="done" if ok_all else "error",
              finished=time.strftime("%H:%M:%S"), message=message)
    log("一键更新结束：%s" % message)


# 对外名字（保持旧调用点可读）
status = _sync_status
start = _start_sync
