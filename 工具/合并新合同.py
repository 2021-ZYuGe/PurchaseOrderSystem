# -*- coding: utf-8 -*-
"""
采购下单系统 · 合并新合同（增量更新）

干什么用的：
    把一批【新合同】加进你现有的产品库，只增不减，不动原有数据。
    适合"又攒了一批新合同，想补进去"的场景。

怎么用：
    双击运行 → 把新合同所在的文件夹路径粘贴进来 → 回车

安全性（三重保险）：
    1. 合并前自动备份 SQLite 数据库及网页缓存
    2. 已收录过的合同记在 SQLite，重复跑同一批不会重复累加
    3. 图片只追加不删除，旧的图一张都不会丢
"""
import csv
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import sqlite_store


def _ensure_console_font():
    """控制台若是点阵字体（不含中文字形），切换成新宋体，避免中文显示成菱形"""
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class CONSOLE_FONT_INFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("nFont", wintypes.DWORD),
                ("dwFontSize", COORD),
                ("FontFamily", wintypes.UINT),
                ("FontWeight", wintypes.UINT),
                ("FaceName", wintypes.WCHAR * 32),
            ]

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        info = CONSOLE_FONT_INFOEX()
        info.cbSize = ctypes.sizeof(info)
        if not kernel.GetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
            return
        if info.FaceName in ("新宋体", "宋体", "SimSun", "Microsoft YaHei Mono"):
            return
        for face in ("新宋体", "SimSun"):
            info.FaceName = face
            if info.dwFontSize.Y <= 0:
                info.dwFontSize.Y = 16
            if kernel.SetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
                return
    except Exception:
        pass


_ensure_console_font()
# 控制台是 Unicode 直接写屏，强转 GBK 反而乱码；只有被管道/文件捕获时才转 GBK。
try:
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="gbk", errors="replace")
        sys.stderr.reconfigure(encoding="gbk", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))      # 工具/
ROOT = os.path.dirname(HERE)                            # 项目根目录
WEB = os.path.join(ROOT, "web")
DATA = os.path.join(WEB, "data.js")
IMG = os.path.join(WEB, "图片")
GEN = os.path.join(HERE, "_工具_生成数据库.py")
REPORT = os.path.join(ROOT, "data", "未导入合同清单.csv")
PY = os.environ.get("CAIGOU_PYTHON") or os.path.join(ROOT, "运行环境", "python.exe")
LOG = os.path.join(ROOT, "data", "_合并日志.txt")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


_QUIET = False


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def pause(msg="\n按回车关闭…"):
    if _QUIET:
        return
    try:
        print(msg)
        input()
    except EOFError:
        pass


def parse_args(argv):
    """支持网页/命令行无交互调用：

        合并新合同.py --files 清单.txt --yes
    """
    opts = {"root": "", "files": "", "yes": False, "allow_copies": False}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--files", "-f") and i + 1 < len(argv):
            opts["files"] = argv[i + 1]
            i += 2
        elif arg in ("--yes", "-y"):
            opts["yes"] = True
            i += 1
        elif arg == "--allow-copies":
            opts["allow_copies"] = True
            i += 1
        elif not opts["root"]:
            opts["root"] = arg
            i += 1
        else:
            i += 1
    return opts


def common_root(paths):
    """一批文件的最上层公共目录，供解析器定位（清单会再过滤一次）"""
    try:
        root = os.path.commonpath([os.path.abspath(p) for p in paths])
    except ValueError:
        root = os.path.dirname(os.path.abspath(paths[0]))
    if not os.path.isdir(root):
        root = os.path.dirname(root)
    return root


def load_data_js(path):
    """严格读取隔离批次输出；损坏或缺少数组会直接报错。"""
    return sqlite_store.read_data_js(path)


def save_data_js(P, S, idx=None, expected_revision=None, expected_idx=None, contracts=None):
    """目录、合同台账与收录索引原子提交，并拒绝覆盖其他任务的更新。"""
    sqlite_store.replace_catalog(
        P, S, imported_index=idx,
        expected_revision=expected_revision,
        expected_imported_index=expected_idx,
        contracts=contracts,
    )


def load_batch_contracts(path):
    """读批次合同台账；缺失或损坏时返回空表，不影响产品合并主流程。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


REPORT_FIELDS = ["合同号", "文件名", "结果", "原因", "供应商", "正文日期", "来源文件", "最近发现"]


def load_batch_results(path):
    """读批次逐份结果（含跳过/失败原因），缺失或损坏时返回空表。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def update_unimported_report(rows, source_root, committed):
    """把本批未导入的合同并入 data\\未导入合同清单.csv。

    committed=True（本批已写入数据库）时，已导入的文件从清单移除；
    失败中止时不动“已导入”项，因为那些合同并没有真正入库。
    """
    existing = {}
    if os.path.exists(REPORT):
        try:
            with open(REPORT, "r", encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    key = (r.get("合同号") or "", r.get("文件名") or "")
                    if key[1]:
                        existing[key] = r
        except Exception:
            existing = {}

    now = time.strftime("%Y-%m-%d %H:%M")
    for r in rows:
        name = str(r.get("文件名") or "").strip()
        if not name:
            continue
        key = (str(r.get("合同号") or ""), name)
        if r.get("结果") == "已导入":
            if committed:
                existing.pop(key, None)
            continue
        existing[key] = {
            "合同号": key[0], "文件名": name,
            "结果": str(r.get("结果") or ""),
            "原因": str(r.get("原因") or ""),
            "供应商": str(r.get("供应商") or ""),
            "正文日期": str(r.get("正文日期") or ""),
            "来源文件": str(r.get("来源文件") or os.path.join(source_root, name)),
            "最近发现": now,
        }

    # 源文件已被移走/删除的条目清掉（目录还在才判断，F 盘离线时保留）
    for key, r in list(existing.items()):
        src = r.get("来源文件") or ""
        if src and os.path.isdir(os.path.dirname(src)) and not os.path.isfile(src):
            existing.pop(key, None)

    # 已收录的合同（例如后来补导成功）从清单移除
    try:
        known = {sqlite_store.contract_no_of(p) for p in sqlite_store.get_imported_index()}
        known.discard("")
    except Exception:
        known = set()
    out = []
    for key, r in existing.items():
        no = r.get("合同号", "")
        if no and no in known:
            continue
        out.append(r)
    out.sort(key=lambda x: (x.get("结果", ""), x.get("合同号", "")))

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(out)
    return len(out)


def report_batch_results(results, source_root, committed):
    if not results:
        return
    try:
        count = update_unimported_report(results, source_root, committed)
        print("未导入清单已更新：data\\未导入合同清单.csv（共 %d 条）" % count)
    except Exception as e:
        print("（未导入清单写入失败：%s）" % e)


def load_index():
    return sqlite_store.get_imported_index()


def collect_docx(root):
    out = []
    for dp, _, names in os.walk(root):
        for n in names:
            if n.lower().endswith(".docx") and not n.startswith("~$"):
                out.append(os.path.join(dp, n))
    return out


def merge(old_P, old_S, new_P, new_S):
    """把批次数据合并进现有数据，返回 (P, S, 新增产品数, 新增供应商数)"""
    # 产品合并键：名称 + 规格
    def pkey(p):
        return (p.get("产品名称", ""), (p.get("规格") or "").strip())

    # 先建立批次 id -> key 的映射（供应商的 产品keys 用的是 id）
    new_pid2key = {p["id"]: pkey(p) for p in new_P}
    old_pid2key = {p["id"]: pkey(p) for p in old_P}

    # ---------- 合并产品 ----------
    pool = {}

    def put(p):
        k = pkey(p)
        if k not in pool:
            pool[k] = {
                "产品名称": p.get("产品名称", ""),
                "规格": p.get("规格", ""),
                "图片": p.get("图片", ""),
                "供应商": list(p.get("供应商", []) or []),
                "历史单价": list(p.get("历史单价", []) or []),
                "分类": list(p.get("分类", []) or []),
                "下单次数": int(p.get("下单次数", 0) or 0),
                "别名": list(p.get("别名", []) or []),
                "备选图片": list(p.get("备选图片", []) or []),
            }
        return pool[k]

    for p in old_P:
        put(p)
    before_p = len(pool)
    for p in new_P:
        already_exists = pkey(p) in pool
        cur = put(p)
        # put() 对全新产品已写入本次次数，只有旧产品才需要累加。
        if already_exists:
            cur["下单次数"] += int(p.get("下单次数", 0) or 0)
        # 价格：新的在前，去重后最多保留 5 个
        merged = list(p.get("历史单价", []) or []) + cur["历史单价"]
        cur["历史单价"] = list(dict.fromkeys(merged))[:5]
        # 图片：原来没有就用新的；不同则为备选图
        if not cur["图片"] and p.get("图片"):
            cur["图片"] = p["图片"]
        elif p.get("图片") and p["图片"] != cur["图片"] and p["图片"] not in cur["备选图片"]:
            cur["备选图片"].append(p["图片"])
        for x in (p.get("备选图片") or []):
            if x not in cur["备选图片"] and x != cur["图片"]:
                cur["备选图片"].append(x)
        for x in (p.get("供应商") or []):
            if x not in cur["供应商"]:
                cur["供应商"].append(x)
        for x in (p.get("分类") or []):
            if x not in cur["分类"]:
                cur["分类"].append(x)
        for x in (p.get("别名") or []):
            if x not in cur["别名"]:
                cur["别名"].append(x)

    # 批次里供应商 -> 产品 的关系补回来（新产品也能反查供应商）
    sup2keys = {}
    for s in old_S:
        sup2keys.setdefault(s.get("供应商名称", ""), set()).update(
            old_pid2key.get(pid) for pid in s.get("产品keys", []) if pid in old_pid2key)
    for s in new_S:
        sup2keys.setdefault(s.get("供应商名称", ""), set()).update(
            new_pid2key.get(pid) for pid in s.get("产品keys", []) if pid in new_pid2key)

    for sup, keys in sup2keys.items():
        for k in keys:
            if k in pool and sup not in pool[k]["供应商"]:
                pool[k]["供应商"].append(sup)

    # 重新分配 id（按下单次数降序，和原来的规则一致）
    items = sorted(pool.items(), key=lambda x: (-x[1]["下单次数"], x[0][0]))
    key2id = {}
    P = []
    for i, (k, v) in enumerate(items, 1):
        pid = "P%04d" % i
        key2id[k] = pid
        P.append({
            "id": pid,
            "产品名称": v["产品名称"],
            "规格": v["规格"],
            "图片": v["图片"],
            "供应商": v["供应商"],
            "历史单价": v["历史单价"],
            "分类": v["分类"],
            "下单次数": v["下单次数"],
            "别名": v["别名"],
            "备选图片": v["备选图片"],
        })

    # ---------- 合并供应商 ----------
    spool = {}
    for s in old_S:
        spool[s.get("供应商名称", "")] = {
            "电话": s.get("电话", ""),
            "主合同日期": s.get("主合同日期", ""),
            "历史合同份数": int(s.get("历史合同份数", 0) or 0),
            "keys": set(k for pid in s.get("产品keys", []) for k in [old_pid2key.get(pid)] if k),
        }
    before_s = len(spool)
    for s in new_S:
        n = s.get("供应商名称", "")
        if n not in spool:
            spool[n] = {"电话": "", "主合同日期": "", "历史合同份数": 0, "keys": set()}
        cur = spool[n]
        cur["历史合同份数"] += int(s.get("历史合同份数", 0) or 0)
        if s.get("电话"):
            cur["电话"] = s["电话"]
        if s.get("主合同日期"):
            cur["主合同日期"] = max(cur["主合同日期"] or "", s["主合同日期"])
        for pid in s.get("产品keys", []):
            if pid in new_pid2key:
                cur["keys"].add(new_pid2key[pid])

    S = []
    for i, (n, v) in enumerate(sorted(spool.items(), key=lambda x: (-x[1]["历史合同份数"], x[0])), 1):
        S.append({
            "id": "S%04d" % i,
            "供应商名称": n,
            "电话": v["电话"],
            "主合同日期": v["主合同日期"],
            "历史合同份数": v["历史合同份数"],
            "产品keys": sorted(key2id[k] for k in v["keys"] if k in key2id),
        })

    return P, S, len(P) - before_p, len(S) - before_s


def load_archive():
    return sqlite_store.get_supplier_archive()


def _archive_tool():
    """按需加载「建立供应商档案.py」的解析能力（复用，不重复造轮子）"""
    src = os.path.join(HERE, "建立供应商档案.py")
    if not os.path.exists(src):
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("supplier_archive", src)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def update_archive(paths):
    """把新合同里的乙方信息补进供应商档案（用于主合同续签自动带入）

    只补不改：已有的公司，仅补它没有的字段；新公司才追加。
    """
    try:
        tool = _archive_tool()
        if tool is None:
            print("  （跳过供应商档案更新：找不到建立供应商档案.py）")
            return
        data = load_archive()
        sup = data.get("供应商") or []
        byname = {}
        for s in sup:
            n = (s.get("名称") or "").strip()
            if n:
                byname[n] = s

        added = updated = 0
        for p in paths:
            try:
                _jia, yi = tool.extract_doc(p)
            except Exception:
                continue
            if not yi:
                continue
            yi = tool.sanitize_record(yi)
            tool.fix_bank_fields(yi)
            name = (yi.get("名称") or "").strip()
            if not name or not tool.looks_like_company(name):
                continue
            yi["来源"] = p
            if name in byname:
                cur = byname[name]
                touched = False
                for k, v in yi.items():
                    if k in ("来源", "最近签署日期"):
                        continue
                    if v and not (cur.get(k) or "").strip():
                        cur[k] = v
                        touched = True
                try:
                    d = yi.get("最近签署日期")
                    if d and d > (cur.get("最近签署日期") or ""):
                        cur["最近签署日期"] = d
                        touched = True
                except Exception:
                    pass
                if touched:
                    updated += 1
            else:
                sup.append(yi)
                byname[name] = yi
                added += 1

        data["供应商"] = sup
        data["_供应商数量"] = len(sup)
        sqlite_store.merge_supplier_profiles(sup, data.get("甲方备选") or {})
        if added or updated:
            print("  供应商档案已更新：新增 %d 家 / 补全 %d 家（共 %d 家）"
                  % (added, updated, len(sup)))
            log("供应商档案更新：+%d 家，补全 %d 家，共 %d"
                % (added, updated, len(sup)))
        else:
            print("  供应商档案无需更新（没有新供应商，也没有缺的新信息）")
    except Exception as e:
        # 档案更新失败绝不能影响主流程（产品合并已完成）
        print("  （供应商档案自动更新失败，不影响本次产品合并：%s）" % e)
        log("供应商档案更新失败：%r" % (e,))


def main():
    global _QUIET
    opts = parse_args(sys.argv[1:])
    _QUIET = bool(opts["yes"] or opts["files"])

    print("=" * 58)
    print("        采购下单系统  合并新合同（增量更新）")
    print("=" * 58)
    print()
    print("说明：把你【新的一批合同】加进现有产品库，")
    print("      原有数据只增不减，图片一张都不会少。")
    print()

    sqlite_store.ensure_database()
    if sqlite_store.product_count() == 0:
        print("[提示] SQLite 中还没有现有数据，将按全新数据来处理。")
    if not os.path.exists(GEN):
        print("[错误] 找不到数据生成工具 _工具_生成数据库.py")
        pause()
        return

    file_list = None
    if opts["files"]:
        try:
            with open(opts["files"], "r", encoding="utf-8") as f:
                file_list = [line.strip() for line in f if line.strip()]
        except OSError as e:
            print("[错误] 读不到待导入清单：%s" % e)
            log("读不到清单：%r" % (e,))
            return
        if not file_list:
            print("清单为空，没有需要处理的合同。")
            return
        root = opts["root"] or common_root(file_list)
        print("本次按系统清单处理 %d 份新合同：" % len(file_list))
        print("  " + root)
    else:
        if opts["root"]:
            root = opts["root"].strip().strip('"').strip("'")
            print("合同路径：%s" % root)
        else:
            print("请把【新合同所在的文件夹，或单个 .docx 文件】路径粘贴进来后回车。")
            print("（已收录过的合同会自动跳过）")
            print()
            root = ask("> ").strip().strip('"').strip("'")
        if os.path.isfile(root):
            if root.lower().endswith(".docx"):
                file_list = [root]
                root = os.path.dirname(root)
                print("本次处理单个文件：%s" % file_list[0])
            else:
                print("\n[错误] 只支持 .docx 文件：%s" % root)
                pause()
                return

    if not os.path.isdir(root):
        print("\n[错误] 找不到这个文件夹：%s" % root)
        pause()
        return

    if file_list is not None:
        missing = [p for p in file_list if not os.path.isfile(p)]
        all_docs = [p for p in file_list if os.path.isfile(p)]
        if missing:
            print("  （有 %d 份文件已不存在，自动跳过）" % len(missing))
    else:
        all_docs = collect_docx(root)

    if not all_docs:
        print("\n[错误] 没有可处理的 .docx 文件。")
        pause()
        return

    idx = {sqlite_store.normalize_path(k): v for k, v in load_index().items()}
    expected_idx = dict(idx)
    expected_revision = sqlite_store.catalog_revision()
    todo = []
    for p in all_docs:
        try:
            st = os.stat(p)
            tag = "%s|%s" % (int(st.st_size), int(st.st_mtime))
        except OSError:
            continue
        if idx.get(sqlite_store.normalize_path(p)) != tag:
            todo.append(p)

    # 同一份合同换了目录（例如指向“便携版\合同下载”）时，按 S 单号识别为副本，
    # 不再重复解析，避免把 641 份副本当成新合同重新导一遍。
    copies = []
    if todo and not opts["allow_copies"]:
        known_no = set()
        for path in idx:
            no = sqlite_store.contract_no_of(path)
            if no:
                known_no.add(no)
        kept = []
        for p in todo:
            no = sqlite_store.contract_no_of(p)
            if no and no in known_no and sqlite_store.normalize_path(p) not in idx:
                copies.append(p)
            else:
                kept.append(p)
        todo = kept

    print()
    print("共找到 %d 份合同，其中：新/有变化 %d 份，之前已收录 %d 份，副本 %d 份（自动跳过）"
          % (len(all_docs), len(todo), len(all_docs) - len(todo) - len(copies), len(copies)))

    if not todo:
        print()
        if copies:
            print("这 %d 份都是已收录合同的副本（单号相同、只是换了目录），不会重复导入。"
                  % len(copies))
        print("没有需要处理的新合同，你的数据已经是最新的了。")
        pause()
        return

    # ---------- 隔离解析：用清单限定范围，不复制原合同，不碰现有数据 ----------
    # 每批使用独立目录，旧批次残留绝不会被误当成本次解析结果。
    tmp = tempfile.mkdtemp(prefix="_增量批次_", dir=HERE)
    os.makedirs(os.path.join(tmp, "web"), exist_ok=True)
    shutil.copy2(GEN, os.path.join(tmp, os.path.basename(GEN)))

    # 只对 generator 暴露"本批次要处理的合同"（generator 输出落在 tmp，不影响正式数据）
    filelist = os.path.join(tmp, "_批次清单.txt")
    with open(filelist, "w", encoding="utf-8") as f:
        for p in todo:
            f.write(p + "\n")

    env = dict(os.environ)
    env["CAIGOU_ONLY"] = filelist

    print()
    print("正在解析 %d 份新合同，请稍候（合同多的时候要几分钟）…" % len(todo))
    log("开始解析 %d 份（源：%s）" % (len(todo), root))
    try:
        result = subprocess.run([PY, os.path.basename(GEN), root], cwd=tmp, env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            details = (result.stdout or "")[-3000:]
            report_batch_results(
                load_batch_results(os.path.join(tmp, "web", "_批次结果.json")),
                root, False,
            )
            raise RuntimeError("合同解析器返回错误码 %d\n%s" % (result.returncode, details))
    except Exception as e:
        print("\n[错误] 解析过程异常：%s" % e)
        log("解析异常：%r" % (e,))
        pause()
        return

    batch_data = os.path.join(tmp, "web", "data.js")
    if not os.path.exists(batch_data):
        print()
        print("[错误] 这批合同没能解析出产品。")
        rows = load_batch_results(os.path.join(tmp, "web", "_批次结果.json"))
        if rows:
            print("      逐份结果：")
            for r in rows[:10]:
                extra = ("（%s）" % r.get("原因")) if r.get("原因") else ""
                print("        · %s → %s%s" % (r.get("文件名", ""), r.get("结果", ""), extra))
            if len(rows) > 10:
                print("        …… 另有 %d 份" % (len(rows) - 10))
        else:
            print("      （解析器没有留下逐份记录，可能是程序文件不完整）")
        print("      常见原因：产品清单是图片、表格格式被改过、或文件带着未接受的修订。")
        print("      你的原有数据未做任何改动。")
        log("批次解析无输出")
        pause()
        return

    new_P, new_S = load_data_js(batch_data)
    if not new_P:
        print("[错误] 本批没有有效产品，正式数据库和收录索引均未改动。")
        pause()
        return
    batch_contracts = load_batch_contracts(os.path.join(tmp, "web", "_批次合同.json"))
    old_P, old_S = sqlite_store.get_catalog()

    print()
    print("这批合同提取到：产品 %d 个 / 供应商 %d 家" % (len(new_P), len(new_S)))
    if batch_contracts:
        print("合同台账：%d 份（含落款签署日期，用于刷新“最近签约”）" % len(batch_contracts))

    # ---------- 先在内存合并，并确保新图片全部就位 ----------
    if os.path.exists(DATA):
        shutil.copy2(DATA, DATA + ".bak")
    P, S, add_p, add_s = merge(old_P, old_S, new_P, new_S)

    src_img = os.path.join(tmp, "web", "图片")
    n_img = 0
    if os.path.exists(src_img):
        os.makedirs(IMG, exist_ok=True)
        for fn in os.listdir(src_img):
            s = os.path.join(src_img, fn)
            if not os.path.isfile(s):
                continue
            dd = os.path.join(IMG, fn)
            temp_img = "%s.%s_%s.tmp" % (dd, os.getpid(), time.time_ns())
            try:
                # 先写临时文件并逐字节校验；旧目标若是残缺文件也会被修复。
                shutil.copy2(s, temp_img)
                if not filecmp.cmp(s, temp_img, shallow=False):
                    raise IOError("图片校验失败：%s" % fn)
                if not os.path.exists(dd) or not filecmp.cmp(s, dd, shallow=False):
                    for attempt in range(20):
                        try:
                            os.replace(temp_img, dd)
                            break
                        except PermissionError:
                            if attempt == 19:
                                raise
                            time.sleep(0.05)
                    n_img += 1
            finally:
                if os.path.exists(temp_img):
                    os.remove(temp_img)

    # ---------- 目录与收录索引在同一个 SQLite 事务中提交 ----------
    batch_results = load_batch_results(os.path.join(tmp, "web", "_批次结果.json"))
    imported_paths = {
        sqlite_store.normalize_path(r["来源文件"])
        for r in batch_results
        if r.get("结果") == "已导入" and r.get("来源文件")
    }
    for p in todo:
        key = sqlite_store.normalize_path(p)
        # 跳过/失败的合同不写入收录索引，下次仍会被复核并保留在未导入清单里
        if batch_results and key not in imported_paths:
            continue
        st = os.stat(p)
        idx[key] = "%s|%s" % (int(st.st_size), int(st.st_mtime))
    save_data_js(P, S, idx, expected_revision, expected_idx, batch_contracts)
    report_batch_results(batch_results, root, True)

    # ---------- 顺手把新合同里的供应商信息补进档案（主合同续签要用） ----------
    print()
    print("正在更新供应商档案（新合同里的联系人/银行信息）…")
    update_archive(todo)

    # 每批临时产物独立保留，不参与后续批次。
    print("   （本批临时文件：%s）" % tmp)
    print()
    log("合并完成：产品 %d（+%d）/ 供应商 %d（+%d）/ 新图 %d"
        % (len(P), add_p, len(S), add_s, n_img))
    print()
    print("=" * 58)
    print("  合并完成！")
    print("    产品库：%d 个（本次新增 %d 个）" % (len(P), add_p))
    print("    供应商：%d 家（本次新增 %d 家）" % (len(S), add_s))
    print("    新图片：%d 张（旧图一张没删）" % n_img)
    try:
        stats = sqlite_store.supplier_contract_stats()
        names = [s.get("供应商名称", "") for s in new_S if s.get("供应商名称")]
        rows = []
        for name in names:
            st = stats.get(name) or {}
            if st.get("最近签约日期"):
                rows.append("      · %s：%s %s" % (
                    name, st["最近签约日期"], st.get("最近合同号", "")))
        if rows:
            print("    本批涉及的供应商，最新签约时间：")
            for line in rows[:10]:
                print(line)
    except Exception:
        pass
    print("    原数据库已备份到 data\\backups，网页缓存备份为 web\\data.js.bak")
    print()
    print("  现在双击桌面【采购下单系统】就能看到新数据了。")
    print("=" * 58)
    pause()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        log("异常：%r" % (e,))
        print()
        print("出错了：%s" % e)
        print("请勿盲目重复操作；目录与收录索引使用同一事务，缓存错误可在重启时自动修复。")
        pause("\n按回车关闭…")
