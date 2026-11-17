# -*- coding: utf-8 -*-
"""数据库结构与迁移：只被 app/infra/store.py 调用。"""
import sqlite3
import time

from app.config import SCHEMA_VERSION as _SCHEMA_VERSION

SCHEMA_VERSION = str(_SCHEMA_VERSION)

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
