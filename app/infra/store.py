# -*- coding: utf-8 -*-
"""采购下单系统 SQLite 数据层。

data/purchase.db 是唯一正式数据源。
P2 之后页面通过 /api/* 实时查库，不再生成 web/data.js 缓存。
仅使用 Python 标准库，所有写操作均在事务中完成。
"""
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import closing, contextmanager, nullcontext
from datetime import date
from pathlib import Path

if __package__ in (None, ''):                 # 允许直接 python app/infra/store.py
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import BACKUP_DIR, DATA_DIR, DATA_JS, DB_PATH, ROOT_PATH as ROOT

SCHEMA_VERSION = "3"
WRITE_LOCK = threading.RLock()


def normalize_path(path):
    """统一路径写法：正斜杠/反斜杠、相对路径都归一，避免同一文件算两份"""
    return os.path.normpath(os.path.abspath(str(path)))

PROFILE_FIELDS = {
    "名称": "name",
    "统一社会信用代码": "credit_code",
    "联系人": "contact",
    "电话": "tel",
    "邮箱": "email",
    "地址": "addr",
    "微信号": "wechat",
    "法定代表人": "legal",
    "对公账户名": "bank_name",
    "对公账号": "bank_account",
    "开户行": "bank_open",
    "最近签署日期": "last_sign",
    "来源": "source",
}
PROFILE_COLUMNS = {v: k for k, v in PROFILE_FIELDS.items()}

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    spec TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT '',
    order_count INTEGER NOT NULL DEFAULT 0 CHECK(order_count >= 0),
    UNIQUE(name, spec)
);
CREATE TABLE IF NOT EXISTS product_prices (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    price REAL NOT NULL,
    PRIMARY KEY(product_id, position)
);
CREATE TABLE IF NOT EXISTS product_aliases (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    alias TEXT NOT NULL,
    PRIMARY KEY(product_id, position)
);
CREATE TABLE IF NOT EXISTS product_categories (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    category TEXT NOT NULL,
    PRIMARY KEY(product_id, position)
);
CREATE TABLE IF NOT EXISTS product_alternative_images (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    filename TEXT NOT NULL,
    PRIMARY KEY(product_id, position)
);
CREATE TABLE IF NOT EXISTS product_supplier_names (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    supplier_name TEXT NOT NULL,
    PRIMARY KEY(product_id, position)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL DEFAULT '',
    main_contract_date TEXT NOT NULL DEFAULT '',
    contract_count INTEGER NOT NULL DEFAULT 0 CHECK(contract_count >= 0)
);
CREATE TABLE IF NOT EXISTS supplier_products (
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY(supplier_id, product_id)
);
CREATE INDEX IF NOT EXISTS idx_supplier_products_product ON supplier_products(product_id);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);

CREATE TABLE IF NOT EXISTS supplier_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    credit_code TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    tel TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    addr TEXT NOT NULL DEFAULT '',
    wechat TEXT NOT NULL DEFAULT '',
    legal TEXT NOT NULL DEFAULT '',
    bank_name TEXT NOT NULL DEFAULT '',
    bank_account TEXT NOT NULL DEFAULT '',
    bank_open TEXT NOT NULL DEFAULT '',
    last_sign TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_supplier_profiles_name ON supplier_profiles(name);
CREATE INDEX IF NOT EXISTS idx_supplier_profiles_last_sign ON supplier_profiles(last_sign DESC);

CREATE TABLE IF NOT EXISTS party_a_profiles (
    name TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_order INTEGER NOT NULL,
    contract_no TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    supplier_name TEXT NOT NULL DEFAULT '',
    main_contract_date TEXT,
    has_order_sheet INTEGER NOT NULL DEFAULT 0,
    order_sheet_start_paragraph INTEGER,
    contract_start_date TEXT NOT NULL DEFAULT '',
    contract_end_date TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_contracts_no ON contracts(contract_no);
CREATE INDEX IF NOT EXISTS idx_contracts_filename ON contracts(filename);

-- 合同有效期的手工登记（老合同正文没写期限、或解析不出来时的兜底）
CREATE TABLE IF NOT EXISTS supplier_contract_terms (
    supplier_name TEXT PRIMARY KEY,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS contract_sign_dates (
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    sign_date TEXT NOT NULL,
    PRIMARY KEY(contract_id, position)
);

CREATE TABLE IF NOT EXISTS supplier_main_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_order INTEGER NOT NULL,
    supplier_name TEXT NOT NULL DEFAULT '',
    latest_main_contract_date TEXT NOT NULL DEFAULT '',
    contract_no TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    contract_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS historical_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_order INTEGER NOT NULL,
    contract_no TEXT NOT NULL DEFAULT '',
    folder TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    supplier_name TEXT NOT NULL DEFAULT '',
    product_name TEXT NOT NULL DEFAULT '',
    spec TEXT NOT NULL DEFAULT '',
    quantity_text TEXT NOT NULL DEFAULT '',
    unit_price_text TEXT NOT NULL DEFAULT '',
    total_amount_text TEXT NOT NULL DEFAULT '',
    remark TEXT NOT NULL DEFAULT '',
    payment_terms TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_history_supplier ON historical_order_items(supplier_name);
CREATE INDEX IF NOT EXISTS idx_history_contract ON historical_order_items(contract_no, filename);

CREATE TABLE IF NOT EXISTS imported_contract_files (
    path TEXT PRIMARY KEY,
    file_size INTEGER NOT NULL,
    mtime INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

-- 结构迁移记录：每个版本只执行一次，失败不会标记
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""


def connect(path=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path or DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # journal_mode 只在初始化时设置；每个并发连接重复切换 WAL 会在 Windows 上争抢锁。
    conn.execute("PRAGMA synchronous = NORMAL")
    # 搜索用：把 Python 的归一化逻辑暴露给 SQL，保证"空格/大小写"处理与前端完全一致
    conn.create_function("norm_text", 1, _norm_text, deterministic=True)
    return conn


@contextmanager
def interprocess_lock(path):
    """短时间的跨进程文件锁；进程异常退出时由操作系统自动释放。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def session(write=False):
    """自动提交/回滚并关闭连接；同一进程内的写事务串行执行。"""
    lock = WRITE_LOCK if write else nullcontext()
    with lock:
        conn = connect()
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            with conn:
                yield conn
        finally:
            conn.close()


def _ensure_columns(conn):
    """老库补列：合同期限是后加的功能，早期库里没有这两列。

    ALTER TABLE 只在缺列时执行一次，重复运行不会报错；
    两个进程同时升级时后一个会拿到「duplicate column」，忽略即可。
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(contracts)")}
    for name, ddl in (("contract_start_date", "TEXT NOT NULL DEFAULT ''"),
                      ("contract_end_date", "TEXT NOT NULL DEFAULT ''")):
        if name in cols:
            continue
        try:
            conn.execute("ALTER TABLE contracts ADD COLUMN %s %s" % (name, ddl))
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
    # 索引必须等列补齐后再建，否则老库执行 SCHEMA 时直接报「no such column」
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_end ON contracts(contract_end_date)")


def init_schema(conn):
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    # 读取操作也经过这里；版本未变化时绝不能产生写事务，避免并发下变成只读连接。
    conn.execute("INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
    row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    if row and row[0] != SCHEMA_VERSION:
        conn.execute("UPDATE schema_meta SET value=? WHERE key='schema_version'", (SCHEMA_VERSION,))


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _m3_drop_legacy(conn):
    """P2：删掉三张历史遗留表。

    只在"旧库已完整导入"（legacy_import_completed 有值且产品非空）时执行，
    执行前 ensure_database 会整库备份，误删也能恢复。
    """
    if not _meta(conn, "legacy_import_completed"):
        return
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        return
    for name in ("legacy_supplier_products", "legacy_products", "legacy_suppliers"):
        if _table_exists(conn, name):
            conn.execute("DROP TABLE " + name)


# (版本号, 名称, 执行函数)；只追加，不修改已发布的条目
MIGRATIONS = [
    (3, "drop_legacy_tables", _m3_drop_legacy),
]


def _applied_migrations(conn):
    if not _table_exists(conn, "schema_migrations"):
        return set()
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def _pending_migrations(conn):
    applied = _applied_migrations(conn)
    return [m for m in MIGRATIONS if m[0] not in applied]


def _apply_migrations(conn):
    """逐个执行待办迁移；每个迁移与它的版本记录在同一事务里。"""
    applied = _applied_migrations(conn)
    for version, name, fn in MIGRATIONS:
        if version in applied:
            continue
        fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?, ?, ?)",
            (version, name, time.strftime("%Y-%m-%d %H:%M:%S")),
        )


def _meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("旧数据文件无法读取，已停止迁移以避免不完整导入：%s（%s）" % (path, exc))


def read_data_js(path=None):
    """读取旧缓存；文件存在但损坏时必须报错，不能把损坏当成空数据。"""
    source = Path(path or DATA_JS)
    if not source.exists():
        return [], []
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("无法读取 %s：%s" % (source, exc))

    def grab(name):
        marker = "const " + name
        start = text.find(marker)
        if start < 0:
            raise RuntimeError("%s 中缺少 %s" % (source, marker))
        start = text.find("[", start + len(marker))
        if start < 0:
            raise RuntimeError("%s 中 %s 不是数组" % (source, marker))
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError as exc:
            raise RuntimeError("%s 中 %s 数据损坏：%s" % (source, marker, exc))
        if not isinstance(value, list):
            raise RuntimeError("%s 中 %s 不是数组" % (source, marker))
        return value

    return grab("PRODUCTS"), grab("SUPPLIERS")


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else []


ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _iso_or_blank(value):
    """只接受 YYYY-MM-DD，其它写法一律当没填，避免脏日期进入到期计算。"""
    text = str(value or "").strip()
    m = ISO_DATE_RE.match(text)
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    if not (1900 <= y <= 2200 and 1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return text


def _insert_catalog(conn, products, suppliers):
    """在一个事务里替换现行目录；其他业务表不受影响。"""
    conn.execute("DELETE FROM suppliers")
    conn.execute("DELETE FROM products")

    product_ids = {}
    supplier_ids = {}
    relation_names = {}

    for s in suppliers:
        cur = conn.execute(
            "INSERT INTO suppliers(code, name, phone, main_contract_date, contract_count) "
            "VALUES(?, ?, ?, ?, ?)",
            (
                str(s.get("id") or ""), str(s.get("供应商名称") or ""),
                str(s.get("电话") or ""), str(s.get("主合同日期") or ""),
                int(s.get("历史合同份数") or 0),
            ),
        )
        supplier_ids[s.get("id")] = cur.lastrowid
        for code in _as_list(s.get("产品keys")):
            relation_names.setdefault(code, []).append(str(s.get("供应商名称") or ""))

    for p in products:
        cur = conn.execute(
            "INSERT INTO products(code, name, spec, image, order_count) VALUES(?, ?, ?, ?, ?)",
            (
                str(p.get("id") or ""), str(p.get("产品名称") or ""),
                str(p.get("规格") or ""), str(p.get("图片") or ""),
                int(p.get("下单次数") or 0),
            ),
        )
        pid = cur.lastrowid
        product_ids[p.get("id")] = pid
        for pos, price in enumerate(_as_list(p.get("历史单价"))):
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue
            conn.execute(
                "INSERT INTO product_prices(product_id, position, price) VALUES(?, ?, ?)",
                (pid, pos, value),
            )
        for table, field, key in (
            ("product_aliases", "alias", "别名"),
            ("product_categories", "category", "分类"),
            ("product_alternative_images", "filename", "备选图片"),
            ("product_supplier_names", "supplier_name", "供应商"),
        ):
            values = _as_list(p.get(key))
            if key == "供应商" and not values:
                values = relation_names.get(p.get("id"), [])
            for pos, value in enumerate(values):
                conn.execute(
                    "INSERT INTO %s(product_id, position, %s) VALUES(?, ?, ?)" % (table, field),
                    (pid, pos, str(value)),
                )

    for s in suppliers:
        sid = supplier_ids.get(s.get("id"))
        if sid is None:
            continue
        for code in s.get("产品keys") or []:
            pid = product_ids.get(code)
            if pid is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO supplier_products(supplier_id, product_id) VALUES(?, ?)",
                    (sid, pid),
                )

    revision = int(_meta(conn, "catalog_revision", "0")) + 1
    _set_meta(conn, "catalog_revision", revision)
    _set_meta(conn, "catalog_updated_at", time.strftime("%Y-%m-%d %H:%M:%S"))


def _upsert_contract_records(conn, records):
    """把增量批次里的合同级记录写进台账（按 文件名 + 供应商 去重）。

    只写合同级信息，不动产品与供应商目录；与目录在同一个事务里提交，
    所以“产品已合并但合同日期没更新”的情况不会出现。
    """
    added = 0
    for record in records:
        filename = str(record.get("文件名") or "").strip()
        supplier = str(record.get("供应商") or "").strip()
        if not filename:
            continue
        no = str(record.get("合同号") or "").strip()
        main = str(record.get("主合同日期") or "").strip()
        term_start = _iso_or_blank(record.get("合同起始"))
        term_end = _iso_or_blank(record.get("合同截止"))
        signs = [str(x).strip() for x in _as_list(record.get("签署日期")) if str(x).strip()]
        row = conn.execute(
            "SELECT id FROM contracts WHERE filename=? AND supplier_name=? ORDER BY id LIMIT 1",
            (filename, supplier),
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO contracts(source_order, contract_no, filename, supplier_name, "
                "main_contract_date, has_order_sheet, order_sheet_start_paragraph, "
                "contract_start_date, contract_end_date) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (0, no, filename, supplier, main or None, 0, None, term_start, term_end),
            )
            cid = cur.lastrowid
            added += 1
        else:
            cid = row["id"]
            # 期限只有解析到才覆盖：老模板没有这条，不能把已登记的日期清空
            conn.execute(
                "UPDATE contracts SET contract_no=?, main_contract_date=?, "
                "contract_start_date=CASE WHEN ?<>'' THEN ? ELSE contract_start_date END, "
                "contract_end_date=CASE WHEN ?<>'' THEN ? ELSE contract_end_date END "
                "WHERE id=?",
                (no or None, main or None, term_start, term_start, term_end, term_end, cid),
            )
        conn.execute("DELETE FROM contract_sign_dates WHERE contract_id=?", (cid,))
        for pos, value in enumerate(signs):
            conn.execute(
                "INSERT INTO contract_sign_dates(contract_id, position, sign_date) VALUES(?, ?, ?)",
                (cid, pos, value),
            )
    return added


def replace_catalog(products, suppliers, backup=True, imported_index=None,
                    expected_revision=None, expected_imported_index=None,
                    contracts=None):
    """替换目录；可选乐观锁防止并发增量任务覆盖彼此的数据。"""
    if backup and DB_PATH.exists():
        backup_database("catalog")
    with WRITE_LOCK, interprocess_lock(DB_PATH.with_name(DB_PATH.name + ".init.lock")):
        with session() as conn:
            init_schema(conn)
        with session(write=True) as conn:
            if expected_revision is not None:
                current = int(_meta(conn, "catalog_revision", "0"))
                if current != int(expected_revision):
                    raise RuntimeError("目录已被另一项更新操作修改，本次已安全中止，请重新运行合并。")
            if expected_imported_index is not None:
                if _read_imported_index(conn) != expected_imported_index:
                    raise RuntimeError("合同收录索引已被另一项更新操作修改，本次已安全中止，请重新运行合并。")
            _insert_catalog(conn, products, suppliers)
            if contracts:
                _upsert_contract_records(conn, contracts)
            if imported_index is not None:
                _write_imported_index(conn, imported_index)
    clear_pending_cache()


def _grouped_rows(conn, sql, key_name, params=()):
    result = {}
    for row in conn.execute(sql, params):
        result.setdefault(row[key_name], []).append(row)
    return result


def _placeholders(count):
    return ",".join("?" * count)


def _hydrate_products(conn, product_rows):
    """把 products 行补全成接口用的字典（价格/别名/分类/备选图/供应商名）。

    传入多少行就只补多少行：搜索时不必把整个产品库都装进内存。
    """
    if not product_rows:
        return []
    ids = [row["id"] for row in product_rows]
    marks = _placeholders(len(ids))
    prices = _grouped_rows(
        conn, "SELECT * FROM product_prices WHERE product_id IN (%s) "
              "ORDER BY product_id, position" % marks, "product_id", ids)
    aliases = _grouped_rows(
        conn, "SELECT * FROM product_aliases WHERE product_id IN (%s) "
              "ORDER BY product_id, position" % marks, "product_id", ids)
    categories = _grouped_rows(
        conn, "SELECT * FROM product_categories WHERE product_id IN (%s) "
              "ORDER BY product_id, position" % marks, "product_id", ids)
    images = _grouped_rows(
        conn, "SELECT * FROM product_alternative_images WHERE product_id IN (%s) "
              "ORDER BY product_id, position" % marks, "product_id", ids)
    sup_names = _grouped_rows(
        conn, "SELECT * FROM product_supplier_names WHERE product_id IN (%s) "
              "ORDER BY product_id, position" % marks, "product_id", ids)

    products = []
    for row in product_rows:
        pid = row["id"]
        products.append({
            "id": row["code"],
            "产品名称": row["name"],
            "规格": row["spec"],
            "图片": row["image"],
            "供应商": [x["supplier_name"] for x in sup_names.get(pid, [])],
            "历史单价": [x["price"] for x in prices.get(pid, [])],
            "分类": [x["category"] for x in categories.get(pid, [])],
            "下单次数": row["order_count"],
            "别名": [x["alias"] for x in aliases.get(pid, [])],
            "备选图片": [x["filename"] for x in images.get(pid, [])],
        })
    return products


def get_catalog():
    if not DB_PATH.exists():
        return [], []
    with session() as conn:
        product_rows = conn.execute(
            "SELECT * FROM products ORDER BY CAST(SUBSTR(code, 2) AS INTEGER), code"
        ).fetchall()
        products = _hydrate_products(conn, product_rows)
        supplier_rows = conn.execute(
            "SELECT * FROM suppliers ORDER BY CAST(SUBSTR(code, 2) AS INTEGER), code"
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT sp.supplier_id, p.code FROM supplier_products sp "
            "JOIN products p ON p.id=sp.product_id ORDER BY p.code"
        ).fetchall()
        relations = {}
        for row in relation_rows:
            relations.setdefault(row["supplier_id"], []).append(row["code"])
        suppliers = []
        stats = supplier_contract_stats()
        for row in supplier_rows:
            st = stats.get(row["name"]) or {}
            main = row["main_contract_date"] or ""
            # 目录与台账可能一新一旧（增量合并/外部同步），统一取较晚的框架合同日期
            latest = max(st.get("最近签约日期") or "", main)
            suppliers.append({
                "id": row["code"],
                "供应商名称": row["name"],
                "电话": row["phone"],
                "主合同日期": latest,
                "最近签约日期": latest,
                "最近合同号": st.get("最近合同号", ""),
                "最近合同文件": st.get("最近合同文件", ""),
                "最近落款日期": st.get("最近落款日期", ""),
                "最近主合同日期": latest,
                "合同记录数": st.get("份数", 0),
                "历史合同份数": row["contract_count"],
                "合同起始日期": st.get("合同起始日期", ""),
                "合同截止日期": st.get("合同截止日期", ""),
                "到期合同号": st.get("到期合同号", ""),
                "到期合同文件": st.get("到期合同文件", ""),
                "期限来源": st.get("期限来源", ""),
                "期限备注": st.get("期限备注", ""),
                "期限待确认": st.get("期限待确认", False),
                "产品keys": relations.get(row["id"], []),
            })
        return products, suppliers


def _empty_contract_stat():
    """单个供应商的合同统计初始值（字段固定，前端可直接取用）"""
    return {
        "份数": 0,
        "主合同日期": "",
        "最近签约日期": "",
        "最近合同号": "",
        "最近合同文件": "",
        "最近落款日期": "",
        "最近主合同日期": "",
        "合同起始日期": "",
        "合同截止日期": "",
        "到期合同号": "",
        "到期合同文件": "",
        "期限来源": "",
        "期限备注": "",
        "期限待确认": False,
        "_有期限签约日": "",
    }


def supplier_contract_stats():
    """按供应商汇总合同台账，供网页展示“最近签约”和“合同到期”。

    业务口径：日期以合同正文“甲乙双方已于…年…月…日签订了《购销框架合同》”
    这句为准，不取文末落款日期。同一日期下优先保留落款更晚、
    单号更大的那份合同，方便追溯是哪一单。

    合同期限（“自…起至…止”）同理：取这家供应商所有合同里止日最晚的一份，
    代表当前覆盖最远的框架合同；如果更新的合同没写期限，标记“期限待确认”，
    避免把已经续签的供应商误报成过期。
    """
    if not DB_PATH.exists():
        return {}
    with session() as conn:
        sign = {
            row["contract_id"]: row["d"]
            for row in conn.execute(
                "SELECT contract_id, MAX(sign_date) AS d FROM contract_sign_dates GROUP BY contract_id"
            )
        }
        manual_terms = {
            row["supplier_name"]: row
            for row in conn.execute("SELECT * FROM supplier_contract_terms")
        }
        stats = {}
        # 手工登记过的供应商，即使台账里一份合同都没有，也要参与到期预警
        for name in manual_terms:
            if name and name not in stats:
                stats[name] = _empty_contract_stat()
        for row in conn.execute("SELECT * FROM contracts"):
            name = (row["supplier_name"] or "").strip()
            if not name:
                continue
            item = stats.get(name)
            if item is None:
                item = stats[name] = _empty_contract_stat()
            item["份数"] += 1
            main = (row["main_contract_date"] or "").strip()
            signed = (sign.get(row["id"]) or "").strip()
            if main > item["主合同日期"]:
                item["主合同日期"] = main
            # 合同期限：跟“最近签约”分开算，签约日期缺失的合同也可能有期限
            end = (row["contract_end_date"] or "").strip()
            if end:
                if main > item["_有期限签约日"]:
                    item["_有期限签约日"] = main
                if end > item["合同截止日期"]:
                    item["合同截止日期"] = end
                    item["合同起始日期"] = (row["contract_start_date"] or "").strip()
                    item["到期合同号"] = row["contract_no"] or ""
                    item["到期合同文件"] = row["filename"] or ""
                    item["期限来源"] = "contract"
            if not main:
                continue
            newer = main > item["最近签约日期"]
            same_day_better = (
                main == item["最近签约日期"]
                and (signed, row["contract_no"] or "") > (item["最近落款日期"], item["最近合同号"])
            )
            if newer or same_day_better:
                item["最近签约日期"] = main
                item["最近合同号"] = row["contract_no"] or ""
                item["最近合同文件"] = row["filename"] or ""
                item["最近落款日期"] = signed
                item["最近主合同日期"] = main

        for name, item in stats.items():
            # 手工登记只在比合同正文更晚时生效：续签后自动值应自动顶上来
            manual = manual_terms.get(name)
            if manual is not None:
                m_end = (manual["end_date"] or "").strip()
                if m_end and m_end >= item["合同截止日期"]:
                    if m_end > item["合同截止日期"] or not item["合同截止日期"]:
                        item["合同截止日期"] = m_end
                        item["合同起始日期"] = (manual["start_date"] or "").strip()
                        item["到期合同号"] = ""
                        item["到期合同文件"] = ""
                        item["期限来源"] = "manual"
                if item["期限来源"] == "manual":
                    item["期限备注"] = (manual["note"] or "").strip()
            # 最近一份合同比“带期限的那份”更新，且自身没写期限 → 提示确认，而不是直接判过期
            latest = item["最近签约日期"]
            base = item["_有期限签约日"] or item["合同截止日期"]
            if item["合同截止日期"] and latest and latest > base:
                newer_row = conn.execute(
                    "SELECT contract_end_date FROM contracts WHERE supplier_name=? "
                    "AND main_contract_date=? ORDER BY id DESC LIMIT 1",
                    (name, latest),
                ).fetchone()
                if newer_row is not None and not (newer_row["contract_end_date"] or "").strip():
                    item["期限待确认"] = True
            item.pop("_有期限签约日", None)
        return stats


EXPIRY_BUCKETS = [
    ("expired", "已过期"),
    ("d3", "3 天内"),
    ("d7", "1 周内"),
    ("d30", "1 个月内"),
    ("d90", "3 个月内"),
    ("d180", "6 个月内"),
    ("ok", "6 个月以上"),
    ("pending", "待确认"),
    ("unknown", "未登记"),
]
EXPIRY_LABELS = dict(EXPIRY_BUCKETS)


def expiry_bucket(days):
    """按剩余自然日分档，和页面上的筛选钮一一对应。"""
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= 3:
        return "d3"
    if days <= 7:
        return "d7"
    if days <= 30:
        return "d30"
    if days <= 90:
        return "d90"
    if days <= 180:
        return "d180"
    return "ok"


def contract_expiry_overview(today=None):
    """合同到期预警：按供应商给出到期日、剩余天数和预警档位。

    数据全部来自 SQLite（合同台账解析出的期限 + 手工登记），
    每次请求现算天数，所以页面放一天再打开也是准的。
    """
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = date.fromisoformat(today[:10])

    stats = supplier_contract_stats()
    if not DB_PATH.exists():
        return {"today": today.isoformat(), "total": 0, "counts": {},
                "buckets": [{"key": k, "label": v, "count": 0} for k, v in EXPIRY_BUCKETS],
                "items": []}
    with session() as conn:
        names = [row["name"] for row in conn.execute("SELECT name FROM suppliers ORDER BY name")]
        # 手工登记过、但目录里还没有的供应商也要列出来
        for row in conn.execute("SELECT supplier_name FROM supplier_contract_terms ORDER BY supplier_name"):
            if row["supplier_name"] and row["supplier_name"] not in names:
                names.append(row["supplier_name"])

    items = []
    for name in names:
        st = stats.get(name) or {}
        end = (st.get("合同截止日期") or "").strip()
        days = None
        if end:
            try:
                days = (date.fromisoformat(end) - today).days
            except ValueError:
                days = None
        bucket = expiry_bucket(days)
        # 已经续签但新合同没写期限的，不直接判过期，挪到「待确认」提醒人工核对
        if bucket == "expired" and st.get("期限待确认"):
            bucket = "pending"
        items.append({
            "供应商": name,
            "到期日": end,
            "起始日": st.get("合同起始日期", ""),
            "剩余天数": days,
            "档位": bucket,
            "档位名": EXPIRY_LABELS.get(bucket, ""),
            "合同号": st.get("到期合同号", ""),
            "合同文件": st.get("到期合同文件", ""),
            "来源": st.get("期限来源", ""),
            "备注": st.get("期限备注", ""),
            "待确认": bool(st.get("期限待确认")),
            "最近签约": st.get("最近签约日期", ""),
            "合同份数": st.get("份数", 0),
        })

    order = {key: i for i, (key, _label) in enumerate(EXPIRY_BUCKETS)}

    def sort_key(x):
        days = x["剩余天数"]
        # 已过期的按“刚过期”排前面，几年前的陈年合同沉到组末
        if x["档位"] == "expired" and days is not None:
            days = -days
        # 未登记里，有框架合同的（需要补期限）排在纯月结供应商前面
        if x["档位"] == "unknown":
            return (order.get("unknown", 99), 0 if x["合同份数"] else 1, x["供应商"])
        return (order.get(x["档位"], 99),
                days if days is not None else 99999,
                x["供应商"])

    items.sort(key=sort_key)
    counts = {}
    for key, _label in EXPIRY_BUCKETS:
        counts[key] = 0
    for it in items:
        counts[it["档位"]] = counts.get(it["档位"], 0) + 1
    return {
        "today": today.isoformat(),
        "total": len(items),
        "counts": counts,
        "buckets": [{"key": k, "label": v, "count": counts.get(k, 0)} for k, v in EXPIRY_BUCKETS],
        "items": items,
    }


def save_contract_term(supplier_name, start_date="", end_date="", note=""):
    """手工登记/修正某家供应商的合同期限。"""
    name = str(supplier_name or "").strip()
    if not name:
        raise ValueError("缺少供应商名称")
    start = _iso_or_blank(start_date)
    end = _iso_or_blank(end_date)
    if start_date and not start:
        raise ValueError("起始日期格式应为 YYYY-MM-DD")
    if end_date and not end:
        raise ValueError("到期日期格式应为 YYYY-MM-DD")
    if not start and not end:
        raise ValueError("请至少填写到期日期")
    if start and end and end < start:
        raise ValueError("到期日期不能早于起始日期")
    with WRITE_LOCK, interprocess_lock(DB_PATH.with_name(DB_PATH.name + ".init.lock")):
        with session() as conn:
            init_schema(conn)
        with session(write=True) as conn:
            conn.execute(
                "INSERT INTO supplier_contract_terms(supplier_name, start_date, end_date, note, updated_at) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(supplier_name) DO UPDATE SET start_date=excluded.start_date, "
                "end_date=excluded.end_date, note=excluded.note, updated_at=excluded.updated_at",
                (name, start, end, str(note or "").strip(), time.strftime("%Y-%m-%d %H:%M:%S")),
            )
    return {"供应商": name, "起始日": start, "到期日": end}


def set_contract_terms(records):
    """批量回填合同期限，records 为 [(contract_id, 起始日, 到期日)]。"""
    rows = [(int(cid), _iso_or_blank(s), _iso_or_blank(e))
            for cid, s, e in records if _iso_or_blank(e)]
    if not rows:
        return 0
    with WRITE_LOCK, interprocess_lock(DB_PATH.with_name(DB_PATH.name + ".init.lock")):
        with session(write=True) as conn:
            conn.executemany(
                "UPDATE contracts SET contract_start_date=?, contract_end_date=? WHERE id=?",
                [(s, e, cid) for cid, s, e in rows],
            )
    return len(rows)


def delete_contract_term(supplier_name):
    """撤销手工登记，回到按合同正文自动识别。"""
    name = str(supplier_name or "").strip()
    if not name:
        raise ValueError("缺少供应商名称")
    with WRITE_LOCK, interprocess_lock(DB_PATH.with_name(DB_PATH.name + ".init.lock")):
        with session(write=True) as conn:
            conn.execute("DELETE FROM supplier_contract_terms WHERE supplier_name=?", (name,))
    return {"供应商": name}


def data_freshness():
    """数据库当前的数据新鲜度：更新于何时、收录了多少份合同。"""
    if not DB_PATH.exists():
        return {}
    with session() as conn:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM schema_meta")}
        files = conn.execute("SELECT COUNT(*) FROM imported_contract_files").fetchone()[0]
        records = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        latest_import = conn.execute("SELECT MAX(updated_at) FROM imported_contract_files").fetchone()[0] or ""
        latest_sign = conn.execute("SELECT MAX(sign_date) FROM contract_sign_dates").fetchone()[0] or ""
        latest_main = conn.execute("SELECT MAX(main_contract_date) FROM contracts").fetchone()[0] or ""
    return {
        "数据更新时间": meta.get("catalog_updated_at", ""),
        "最近导入": latest_import,
        "合同记录": records,
        "已收录文件": files,
        "最近落款": latest_sign,
        "最近主合同": latest_main,
    }


CONTRACT_NO_RE = re.compile(r"(S\d{8})", re.I)
CONTRACT_EXTS = (".docx",)
_PENDING_LOCK = threading.Lock()
_PENDING_CACHE = {"at": 0.0, "data": None}
_PENDING_TTL = 30.0


def contract_no_of(path):
    """从文件名或所在文件夹名提取 S 单号。

    易快报归档是「S单号/合同.docx」，下载目录是「S单号_合同.docx」，
    两种结构都要认，否则同一份合同换个目录就会被当成新文件。
    """
    text = str(path)
    candidates = [os.path.basename(text)]
    parent = os.path.dirname(text)
    if parent:
        candidates.append(os.path.basename(parent))
    for value in candidates:
        match = CONTRACT_NO_RE.search(value)
        if match:
            return match.group(1).upper()
    return ""


def _candidate_contract_dirs():
    """已知的合同来源目录：历史导入目录 + 本机易快报下载目录。

    历史目录是「来源根/S26013014/合同.docx」，根要再往上一层；
    下载目录是「合同下载/S26014483_合同.docx」扁平结构，根就是它自己。
    """
    dirs = []
    seen = set()

    def add(path):
        if not path:
            return
        key = os.path.normcase(os.path.abspath(str(path)))
        if key not in seen:
            seen.add(key)
            dirs.append(str(path))

    try:
        for path in get_imported_index().keys():
            parent = os.path.dirname(str(path))
            if CONTRACT_NO_RE.fullmatch(os.path.basename(parent).strip()):
                add(os.path.dirname(parent))
            else:
                add(parent)
    except Exception:
        pass
    home = Path.home()
    for parts in (("Desktop", "易快报合同下载", "合同下载"),
                  ("Desktop", "合同下载")):
        cand = home.joinpath(*parts)
        if cand.is_dir():
            add(str(cand))
    return dirs


def clear_pending_cache():
    with _PENDING_LOCK:
        _PENDING_CACHE["at"] = 0.0
        _PENDING_CACHE["data"] = None


def scan_pending_contracts():
    """扫描合同来源目录，找出还没进系统的合同（按合同号识别，副本换了目录也能认）。"""
    with _PENDING_LOCK:
        cached = _PENDING_CACHE.get("data")
        if cached and time.time() - _PENDING_CACHE.get("at", 0) < _PENDING_TTL:
            return cached

    index = get_imported_index()
    known_no, known_name, known_path = set(), set(), set()
    for path in index:
        no = contract_no_of(path)
        if no:
            known_no.add(no)
        known_name.add(os.path.basename(str(path)).lower())
        known_path.add(os.path.abspath(str(path)).lower())

    checked, missing, pending = [], [], []
    seen = set()
    for root in _candidate_contract_dirs():
        if not os.path.isdir(root):
            missing.append(root)
            continue
        checked.append(root)
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                low = name.lower()
                if not low.endswith(CONTRACT_EXTS) or name.startswith("~$"):
                    continue
                full = os.path.join(dirpath, name)
                no = contract_no_of(full)
                if no and no in known_no:
                    continue
                if not no and (low in known_name or os.path.abspath(full).lower() in known_path):
                    continue
                tag = no or low
                if tag in seen:
                    continue
                seen.add(tag)
                try:
                    stat = os.stat(full)
                except OSError:
                    continue
                pending.append({
                    "文件名": name,
                    "路径": full,
                    "根": root,
                    "合同号": no,
                    "大小": stat.st_size,
                    "修改时间": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    "_mtime": stat.st_mtime,
                })
    pending.sort(key=lambda x: x["_mtime"], reverse=True)
    newest = pending[0] if pending else {}
    data = {
        "已检查目录": checked,
        "不可用目录": missing,
        "待导入数量": len(pending),
        "最新文件": newest.get("文件名", ""),
        "最新日期": newest.get("修改时间", ""),
        "待导入样例": [p["文件名"] for p in pending[:8]],
        "路径清单": [{"路径": p["路径"], "根": p["根"]} for p in pending[:500]],
        "检查时间": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _PENDING_LOCK:
        _PENDING_CACHE["at"] = time.time()
        _PENDING_CACHE["data"] = data
    return data


def product_count():
    if not DB_PATH.exists():
        return 0
    with session() as conn:
        return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]


def catalog_revision():
    if not DB_PATH.exists():
        return 0
    with session() as conn:
        return int(_meta(conn, "catalog_revision", "0"))


def database_stamp():
    if not DB_PATH.exists():
        return "0"
    with session() as conn:
        revision = _meta(conn, "catalog_revision", "0")
    stat = DB_PATH.stat()
    return "%s_%d_%d" % (revision, int(stat.st_size), int(stat.st_mtime))


def backup_database(reason="manual"):
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S") + ("_%06d" % (time.time_ns() % 1000000))
    target = BACKUP_DIR / ("purchase_%s_%s.db" % (stamp, reason))
    with closing(connect()) as source, closing(sqlite3.connect(str(target))) as dest:
        source.backup(dest)
    return str(target)


def restore_database(backup_path):
    if not os.path.isfile(backup_path):
        raise FileNotFoundError(backup_path)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with WRITE_LOCK, closing(sqlite3.connect(str(backup_path))) as source, closing(connect()) as dest:
        source.backup(dest)


def _read_imported_index(conn):
    rows = conn.execute("SELECT path, file_size, mtime FROM imported_contract_files").fetchall()
    index = {}
    for r in rows:
        index[normalize_path(r["path"])] = "%d|%d" % (r["file_size"], r["mtime"])
    return index


def get_imported_index():
    if not DB_PATH.exists():
        return {}
    with session() as conn:
        return _read_imported_index(conn)


def _write_imported_index(conn, index):
    conn.execute("DELETE FROM imported_contract_files")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    normalized = {}
    for path, tag in index.items():
        normalized[normalize_path(path)] = tag
    for path, tag in normalized.items():
        size, mtime = str(tag).rsplit("|", 1)
        conn.execute(
            "INSERT INTO imported_contract_files(path, file_size, mtime, updated_at) VALUES(?, ?, ?, ?)",
            (path, int(size), int(mtime), now),
        )


def save_imported_index(index):
    with session(write=True) as conn:
        _write_imported_index(conn, index)


def _profile_row(row):
    return {cn: row[col] for cn, col in PROFILE_FIELDS.items()}


def list_supplier_profiles():
    if not DB_PATH.exists():
        return []
    with session() as conn:
        rows = conn.execute(
            "SELECT * FROM supplier_profiles ORDER BY last_sign DESC, id"
        ).fetchall()
        return [_profile_row(r) for r in rows]


def get_supplier_archive():
    suppliers = list_supplier_profiles()
    party_a = {}
    if DB_PATH.exists():
        with session() as conn:
            for row in conn.execute("SELECT name, payload FROM party_a_profiles"):
                try:
                    party_a[row["name"]] = json.loads(row["payload"])
                except ValueError:
                    pass
    return {
        "_说明": "SQLite 正式数据源；原 JSON 仅作迁移备份",
        "_供应商数量": len(suppliers),
        "甲方备选": party_a,
        "供应商": suppliers,
    }


def save_supplier_profile(info):
    name = str(info.get("name") or "").strip()
    if not name:
        return False
    values = {"名称": name}
    for key, value in info.items():
        if key == "name" or not value:
            continue
        values[PROFILE_COLUMNS.get(key, key)] = str(value).strip()
    values["最近签署日期"] = time.strftime("%Y-%m-%d")
    with session(write=True) as conn:
        row = conn.execute(
            "SELECT id FROM supplier_profiles WHERE name=? ORDER BY id LIMIT 1", (name,)
        ).fetchone()
        if row is None:
            columns = [PROFILE_FIELDS[k] for k in values if k in PROFILE_FIELDS]
            params = [values[k] for k in values if k in PROFILE_FIELDS]
            conn.execute(
                "INSERT INTO supplier_profiles(%s) VALUES(%s)" %
                (",".join(columns), ",".join("?" for _ in columns)), params,
            )
        else:
            assignments, params = [], []
            for cn, value in values.items():
                col = PROFILE_FIELDS.get(cn)
                if col and col != "name":
                    assignments.append(col + "=?")
                    params.append(value)
            params.append(row["id"])
            conn.execute(
                "UPDATE supplier_profiles SET %s WHERE id=?" % ",".join(assignments), params
            )
    return True


def merge_supplier_profiles(records, party_a=None):
    added = updated = 0
    with session(write=True) as conn:
        for record in records:
            name = str(record.get("名称") or "").strip()
            if not name:
                continue
            row = conn.execute(
                "SELECT * FROM supplier_profiles WHERE name=? ORDER BY id LIMIT 1", (name,)
            ).fetchone()
            if row is None:
                columns, params = ["name"], [name]
                for cn, col in PROFILE_FIELDS.items():
                    if cn == "名称":
                        continue
                    columns.append(col)
                    params.append(str(record.get(cn) or ""))
                conn.execute(
                    "INSERT INTO supplier_profiles(%s) VALUES(%s)" %
                    (",".join(columns), ",".join("?" for _ in columns)), params,
                )
                added += 1
                continue
            assignments, params = [], []
            touched = False
            for cn, col in PROFILE_FIELDS.items():
                if cn in ("名称", "最近签署日期", "来源"):
                    continue
                new = str(record.get(cn) or "")
                if new and not str(row[col] or "").strip():
                    assignments.append(col + "=?")
                    params.append(new)
                    touched = True
            new_date = str(record.get("最近签署日期") or "")
            if new_date and new_date > str(row["last_sign"] or ""):
                assignments.append("last_sign=?")
                params.append(new_date)
                if record.get("来源"):
                    assignments.append("source=?")
                    params.append(str(record["来源"]))
                touched = True
            elif not row["source"] and record.get("来源"):
                assignments.append("source=?")
                params.append(str(record["来源"]))
                touched = True
            if touched:
                params.append(row["id"])
                conn.execute(
                    "UPDATE supplier_profiles SET %s WHERE id=?" % ",".join(assignments), params
                )
                updated += 1
        for name, payload in (party_a or {}).items():
            conn.execute(
                "INSERT INTO party_a_profiles(name, payload) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (name, json.dumps(payload, ensure_ascii=False)),
            )
    return added, updated


def get_contract_records():
    if not DB_PATH.exists():
        return []
    with session() as conn:
        dates = _grouped_rows(
            conn, "SELECT * FROM contract_sign_dates ORDER BY contract_id, position", "contract_id"
        )
        rows = conn.execute("SELECT * FROM contracts ORDER BY source_order, id").fetchall()
        return [{
            "合同号": r["contract_no"],
            "文件名": r["filename"],
            "供应商": r["supplier_name"],
            "主合同日期": r["main_contract_date"],
            "签署日期": [d["sign_date"] for d in dates.get(r["id"], [])],
            "有订购清单页": bool(r["has_order_sheet"]),
            "订购清单起始段": r["order_sheet_start_paragraph"],
        } for r in rows]


def get_historical_order_items():
    if not DB_PATH.exists():
        return []
    with session() as conn:
        rows = conn.execute("SELECT * FROM historical_order_items ORDER BY source_order, id").fetchall()
        return [{
            "合同号": r["contract_no"], "文件夹": r["folder"], "文件名": r["filename"],
            "供应商": r["supplier_name"], "产品名称": r["product_name"], "规格": r["spec"],
            "数量": r["quantity_text"], "单价": r["unit_price_text"],
            "总金额": r["total_amount_text"], "备注": r["remark"],
            "付款方式": r["payment_terms"], "图片": r["image"],
        } for r in rows]


def _history_source_signature():
    parts = []
    for name in ("供应商主合同信息.json", "合同提取记录.json"):
        path = DATA_DIR / name
        try:
            stat = path.stat()
            parts.append("%s:%d:%d" % (name, stat.st_size, stat.st_mtime_ns))
        except OSError:
            parts.append(name + ":missing")
    return "|".join(parts)


def _replace_history_sources(conn):
    """历史 JSON 若由原有外部工具更新，则同步到 SQLite。

    合同台账采用增量更新：已存在的按「文件名 + 合同号」更新，不删除
    增量导入进来、但旧 JSON 里没有的合同，避免换电脑/外部工具刷新时丢数据。
    """
    main_info = _read_json(DATA_DIR / "供应商主合同信息.json", {})
    history = _read_json(DATA_DIR / "合同提取记录.json", [])
    conn.execute("DELETE FROM supplier_main_contracts")
    conn.execute("DELETE FROM historical_order_items")
    for index, record in enumerate(main_info.get("合同记录") or []):
        contract_no = str(record.get("合同号") or "")
        filename = str(record.get("文件名") or "")
        supplier = str(record.get("供应商") or "")
        main_date = record.get("主合同日期")
        has_sheet = 1 if record.get("有订购清单页") else 0
        sheet_start = record.get("订购清单起始段")
        row = conn.execute(
            "SELECT id FROM contracts WHERE filename=? AND IFNULL(contract_no, '')=? "
            "ORDER BY id LIMIT 1",
            (filename, contract_no),
        ).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO contracts(source_order, contract_no, filename, supplier_name, "
                "main_contract_date, has_order_sheet, order_sheet_start_paragraph) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (index, contract_no, filename, supplier, main_date, has_sheet, sheet_start),
            )
            cid = cur.lastrowid
        else:
            cid = row[0]
            conn.execute(
                "UPDATE contracts SET source_order=?, supplier_name=?, main_contract_date=?, "
                "has_order_sheet=?, order_sheet_start_paragraph=? WHERE id=?",
                (index, supplier, main_date, has_sheet, sheet_start, cid),
            )
            conn.execute("DELETE FROM contract_sign_dates WHERE contract_id=?", (cid,))
        for pos, value in enumerate(record.get("签署日期") or []):
            conn.execute(
                "INSERT INTO contract_sign_dates(contract_id, position, sign_date) VALUES(?, ?, ?)",
                (cid, pos, str(value)),
            )
    for index, record in enumerate(main_info.get("供应商主合同") or []):
        conn.execute(
            "INSERT INTO supplier_main_contracts(source_order, supplier_name, latest_main_contract_date, "
            "contract_no, filename, contract_count) VALUES(?, ?, ?, ?, ?, ?)",
            (
                index, str(record.get("供应商") or ""), str(record.get("最新主合同日期") or ""),
                str(record.get("合同号") or ""), str(record.get("文件名") or ""),
                int(record.get("合同份数") or 0),
            ),
        )
    fields = (
        ("合同号", "contract_no"), ("文件夹", "folder"), ("文件名", "filename"),
        ("供应商", "supplier_name"), ("产品名称", "product_name"), ("规格", "spec"),
        ("数量", "quantity_text"), ("单价", "unit_price_text"),
        ("总金额", "total_amount_text"), ("备注", "remark"),
        ("付款方式", "payment_terms"), ("图片", "image"),
    )
    for index, record in enumerate(history):
        columns = ["source_order"] + [col for _cn, col in fields]
        params = [index] + [str(record.get(cn) or "") for cn, _col in fields]
        conn.execute(
            "INSERT INTO historical_order_items(%s) VALUES(%s)" %
            (",".join(columns), ",".join("?" for _ in columns)), params,
        )
    _set_meta(conn, "history_source_signature", _history_source_signature())


def _migrate_legacy(conn):
    products, suppliers = read_data_js()
    if products or suppliers:
        _insert_catalog(conn, products, suppliers)

    archive = _read_json(DATA_DIR / "供应商档案.json", {})
    for index, record in enumerate(archive.get("供应商") or []):
        columns, params = [], []
        for cn, col in PROFILE_FIELDS.items():
            columns.append(col)
            params.append(str(record.get(cn) or ""))
        conn.execute(
            "INSERT INTO supplier_profiles(%s) VALUES(%s)" %
            (",".join(columns), ",".join("?" for _ in columns)), params,
        )
    for name, payload in (archive.get("甲方备选") or {}).items():
        conn.execute(
            "INSERT OR REPLACE INTO party_a_profiles(name, payload) VALUES(?, ?)",
            (name, json.dumps(payload, ensure_ascii=False)),
        )

    _replace_history_sources(conn)

    imported = _read_json(DATA_DIR / "_已收录合同.json", {})
    _write_imported_index(conn, imported)

    if not _table_exists(conn, "legacy_products"):
        return                       # P2 之后新库不再建遗留表，直接跳过这段

    for record in _read_json(DATA_DIR / "产品主库.json", []):
        conn.execute(
            "INSERT OR REPLACE INTO legacy_products(legacy_id, name, spec, occurrence_count, "
            "suppliers_json, categories_json, prices_json, aliases_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(record.get("id") or ""), str(record.get("产品名称") or ""),
                str(record.get("规格") or ""), int(record.get("出现次数") or 0),
                json.dumps(record.get("供应商列表") or [], ensure_ascii=False),
                json.dumps(record.get("项目分类") or [], ensure_ascii=False),
                json.dumps(record.get("历史价格") or [], ensure_ascii=False),
                json.dumps(record.get("别名") or [], ensure_ascii=False),
            ),
        )
    legacy_suppliers = _read_json(DATA_DIR / "供应商主库.json", [])
    for record in legacy_suppliers:
        name = str(record.get("供应商名称") or "")
        conn.execute(
            "INSERT OR REPLACE INTO legacy_suppliers(name, phone, product_count) VALUES(?, ?, ?)",
            (name, str(record.get("电话") or ""), int(record.get("产品数") or 0)),
        )
    for record in legacy_suppliers:
        for pos, legacy_id in enumerate(record.get("产品keys") or []):
            conn.execute(
                "INSERT OR REPLACE INTO legacy_supplier_products(supplier_name, position, legacy_product_id) "
                "VALUES(?, ?, ?)",
                (str(record.get("供应商名称") or ""), pos, str(legacy_id)),
            )


def ensure_database():
    """首次启动自动迁移；标记检查和迁移在同一立即写事务中。"""
    existed = DB_PATH.exists()
    with WRITE_LOCK, interprocess_lock(DB_PATH.with_name(DB_PATH.name + ".init.lock")):
        with session() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            init_schema(conn)
            pending = _pending_migrations(conn)
        # 有结构迁移时先整库备份，再动表
        if pending and existed:
            backup_database("before_migration_v%d" % pending[0][0])
        with session(write=True) as conn:
            migrated = _meta(conn, "legacy_import_completed")
            if not migrated:
                _migrate_legacy(conn)
                _set_meta(conn, "legacy_import_completed", time.strftime("%Y-%m-%d %H:%M:%S"))
            _apply_migrations(conn)
            history_files = (DATA_DIR / "供应商主合同信息.json", DATA_DIR / "合同提取记录.json")
            if all(path.exists() for path in history_files):
                if _meta(conn, "history_source_signature") != _history_source_signature():
                    _replace_history_sources(conn)
    return str(DB_PATH)


def database_counts():
    if not DB_PATH.exists():
        return {}
    names = (
        "products", "suppliers", "supplier_products", "supplier_profiles", "contracts",
        "contract_sign_dates", "supplier_main_contracts", "historical_order_items",
        "imported_contract_files",
    )
    with session() as conn:
        available = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return {name: conn.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
                for name in names if name in available}


def verify_database():
    if not DB_PATH.exists():
        raise RuntimeError("数据库不存在：%s" % DB_PATH)
    with session() as conn:
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        invalid_relations = conn.execute(
            "SELECT COUNT(*) FROM supplier_products sp "
            "LEFT JOIN products p ON p.id=sp.product_id "
            "LEFT JOIN suppliers s ON s.id=sp.supplier_id "
            "WHERE p.id IS NULL OR s.id IS NULL"
        ).fetchone()[0]
        duplicate_codes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT code FROM products GROUP BY code HAVING COUNT(*)>1)"
        ).fetchone()[0]
        if integrity != "ok" or foreign_key_errors or invalid_relations or duplicate_codes:
            raise RuntimeError(
                "数据库校验失败：integrity=%s, foreign_keys=%d, relations=%d, duplicate_codes=%d" %
                (integrity, len(foreign_key_errors), invalid_relations, duplicate_codes)
            )
        return {"integrity": integrity, "foreign_key_errors": 0, "invalid_relations": 0}


# ---------------- 只读查询：前端按需取数（P2 起 data.js 退场） ----------------

def _norm_text(value):
    """与前端 norm() 一致：转小写、去掉所有空白"""
    return re.sub(r"\s+", "", str(value or "")).lower()


def _product_hit(product, q, raw_len):
    """与前端 prodHit() 一致：名称 / 别名 / （2 字以上）规格"""
    if q in _norm_text(product.get("产品名称")):
        return True
    if any(q in _norm_text(alias) for alias in (product.get("别名") or [])):
        return True
    if raw_len >= 2 and q in _norm_text(product.get("规格")):
        return True
    return False


def catalog_meta():
    """页面首屏需要的轻量统计，不包含任何明细"""
    counts = database_counts()
    with session() as conn:
        with_image = conn.execute(
            "SELECT COUNT(*) FROM products WHERE image <> ''").fetchone()[0]
        updated = _meta(conn, "catalog_updated_at", "")
    return {
        "products": counts.get("products", 0),
        "suppliers": counts.get("suppliers", 0),
        "with_image": with_image,
        "updated": updated,
        "revision": catalog_revision(),
        "stamp": database_stamp(),
    }


def list_suppliers_light():
    """供应商下拉用的轻量列表：只有名字、电话、最近签约和产品 keys"""
    if not DB_PATH.exists():
        return []
    stats = supplier_contract_stats()
    with session() as conn:
        rows = conn.execute(
            "SELECT id, code, name, phone, main_contract_date, contract_count FROM suppliers "
            "ORDER BY CAST(SUBSTR(code, 2) AS INTEGER), code").fetchall()
        relations = {}
        for row in conn.execute(
                "SELECT sp.supplier_id, p.code FROM supplier_products sp "
                "JOIN products p ON p.id = sp.product_id ORDER BY p.code"):
            relations.setdefault(row["supplier_id"], []).append(row["code"])
    result = []
    for row in rows:
        st = stats.get(row["name"]) or {}
        latest = max(st.get("最近签约日期") or "", row["main_contract_date"] or "")
        result.append({
            "id": row["code"],
            "供应商名称": row["name"],
            "电话": row["phone"],
            "最近签约日期": latest,
            "主合同日期": latest,
            "最近合同号": st.get("最近合同号", ""),
            "合同记录数": int(st.get("份数") or 0),
            "历史合同份数": int(row["contract_count"] or 0),
            "产品keys": relations.get(row["id"], []),
        })
    return result


def _like_escape(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_products(query, supplier_code=None, limit=20):
    """产品搜索：过滤下推到 SQLite，只回填命中的行。

    命中规则与前端原来的本地搜索一致：名称 / 别名 / 2 字以上规格；
    排序：该供应商的产品 → 有图 → 下单次数。
    """
    raw = str(query or "").strip()
    q = _norm_text(raw)
    if not q:
        return []
    like = "%" + _like_escape(q) + "%"
    sql = (
        "SELECT p.* FROM products p WHERE "
        "norm_text(p.name) LIKE ? ESCAPE '\\' "
        "OR EXISTS (SELECT 1 FROM product_aliases a "
        "           WHERE a.product_id = p.id AND norm_text(a.alias) LIKE ? ESCAPE '\\') "
        "OR (? >= 2 AND norm_text(p.spec) LIKE ? ESCAPE '\\') "
        "ORDER BY CAST(SUBSTR(p.code, 2) AS INTEGER), p.code"
    )
    limit = max(1, int(limit or 20))
    sup_keys = set()
    with session() as conn:
        if supplier_code:
            row = conn.execute(
                "SELECT id FROM suppliers WHERE code = ?", (supplier_code,)).fetchone()
            if row:
                sup_keys = {r[0] for r in conn.execute(
                    "SELECT p.code FROM supplier_products sp "
                    "JOIN products p ON p.id = sp.product_id WHERE sp.supplier_id = ?",
                    (row["id"],))}
        rows = conn.execute(sql, (like, like, len(raw), like)).fetchall()
        rows.sort(key=lambda r: (
            0 if r["code"] in sup_keys else 1,
            0 if r["image"] else 1,
            -int(r["order_count"] or 0),
        ))
        return _hydrate_products(conn, rows[:limit])


def search_suppliers(query):
    """供应商下拉的本地过滤；不传关键字时返回全部（轻量字段）"""
    items = list_suppliers_light()
    q = _norm_text(query)
    if not q:
        return items
    return [s for s in items if q in _norm_text(s["供应商名称"])]


def schema_info():
    """当前程序要求的结构版本 + 已应用的迁移版本"""
    with session() as conn:
        applied = [r[0] for r in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version")]
    return {"current": SCHEMA_VERSION, "applied": applied}
