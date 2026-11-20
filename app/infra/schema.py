# -*- coding: utf-8 -*-
"""数据库结构与迁移：只被 app/infra/store.py 调用。"""
import json
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
    name_key TEXT NOT NULL DEFAULT '',
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
    name_key TEXT NOT NULL DEFAULT '',
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
    party_a TEXT NOT NULL DEFAULT '',
    party_a_source TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
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

-- 按“供应商 + 甲方”登记期限；party_a 为空表示未确认甲方
CREATE TABLE IF NOT EXISTS supplier_party_terms (
    supplier_name TEXT NOT NULL,
    party_a TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(supplier_name, party_a)
);

-- 供应商合并留痕
CREATE TABLE IF NOT EXISTS supplier_merge_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    products INTEGER NOT NULL DEFAULT 0,
    contracts INTEGER NOT NULL DEFAULT 0,
    profiles INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
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


_COLUMNS = {
    "contracts": (
        ("contract_start_date", "TEXT NOT NULL DEFAULT ''"),
        ("contract_end_date", "TEXT NOT NULL DEFAULT ''"),
        ("party_a", "TEXT NOT NULL DEFAULT ''"),
        ("party_a_source", "TEXT NOT NULL DEFAULT ''"),
        ("source_path", "TEXT NOT NULL DEFAULT ''"),
    ),
    "suppliers": (("name_key", "TEXT NOT NULL DEFAULT ''"),),
    "supplier_profiles": (("name_key", "TEXT NOT NULL DEFAULT ''"),),
}


def _ensure_columns(conn):
    """老库补列：ALTER TABLE 只在缺列时执行一次。

    两个进程同时升级时后一个会拿到「duplicate column」，忽略即可。
    """
    for table, columns in _COLUMNS.items():
        existing = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, ddl in columns:
            if name in existing:
                continue
            try:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
    # 索引必须等列补齐后再建，否则老库执行 SCHEMA 时直接报「no such column」
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_end ON contracts(contract_end_date)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_supplier_profiles_key ON supplier_profiles(name_key)")


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


PARTY_A_SEED = {
    "广州兴趣岛信息科技有限公司": {
        "name": "广州兴趣岛信息科技有限公司",
        "short": "兴趣岛",
        "credit_code": "91440104MA59C33C5N",
        "contact": "简丽冰",
        "tel": "15814464431",
        "email": "457263395@qq.com",
        "addr": "广州市天河区奥体南路9号兴创楼二楼203供应链组",
    },
    "广州普惠优品电子商贸有限公司": {
        "name": "广州普惠优品电子商贸有限公司",
        "short": "普惠优品",
        "credit_code": "91440106MA7LKA4517",
        "contact": "简丽冰",
        "tel": "15814464431",
        "email": "457263395@qq.com",
        "addr": "广州市天河区奥体南路9号兴创楼二楼203供应链组",
    },
}

_PROFILE_TEXT_COLUMNS = (
    "credit_code", "contact", "tel", "email", "addr", "wechat", "legal",
    "bank_name", "bank_account", "bank_open", "source",
)


def _merge_supplier_rows(conn, keep, dup):
    """把 dup 的产品、合同、期限、旧期限全部挂到 keep 上。"""
    keep_id, dup_id = keep["id"], dup["id"]
    keep_name, dup_name = keep["name"], dup["name"]
    conn.execute(
        "INSERT OR IGNORE INTO supplier_products(supplier_id, product_id) "
        "SELECT ?, product_id FROM supplier_products WHERE supplier_id=?",
        (keep_id, dup_id),
    )
    conn.execute("DELETE FROM supplier_products WHERE supplier_id=?", (dup_id,))
    conn.execute("UPDATE contracts SET supplier_name=? WHERE supplier_name=?",
                 (keep_name, dup_name))
    conn.execute("UPDATE historical_order_items SET supplier_name=? WHERE supplier_name=?",
                 (keep_name, dup_name))
    conn.execute("UPDATE supplier_main_contracts SET supplier_name=? WHERE supplier_name=?",
                 (keep_name, dup_name))
    conn.execute("UPDATE product_supplier_names SET supplier_name=? WHERE supplier_name=?",
                 (keep_name, dup_name))
    for term in conn.execute(
            "SELECT * FROM supplier_party_terms WHERE supplier_name=?", (dup_name,)).fetchall():
        current = conn.execute(
            "SELECT * FROM supplier_party_terms WHERE supplier_name=? AND party_a=?",
            (keep_name, term["party_a"]),
        ).fetchone()
        if current and (current["end_date"] or "") >= (term["end_date"] or ""):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO supplier_party_terms"
            "(supplier_name, party_a, start_date, end_date, note, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (keep_name, term["party_a"], term["start_date"], term["end_date"],
             term["note"], term["updated_at"]),
        )
    conn.execute("DELETE FROM supplier_party_terms WHERE supplier_name=?", (dup_name,))
    old = conn.execute(
        "SELECT * FROM supplier_contract_terms WHERE supplier_name=?", (dup_name,)).fetchone()
    if old:
        conn.execute(
            "INSERT OR IGNORE INTO supplier_contract_terms"
            "(supplier_name, start_date, end_date, note, updated_at) VALUES(?, ?, ?, ?, ?)",
            (keep_name, old["start_date"], old["end_date"], old["note"], old["updated_at"]),
        )
        conn.execute("DELETE FROM supplier_contract_terms WHERE supplier_name=?", (dup_name,))
    if not str(keep["phone"] or "").strip() and str(dup["phone"] or "").strip():
        conn.execute("UPDATE suppliers SET phone=? WHERE id=?", (dup["phone"], keep_id))
    conn.execute("DELETE FROM suppliers WHERE id=?", (dup_id,))


def _m4_party_a_and_name_key(conn):
    """v4：名称归一键、按甲方期限表、精确重复合并、甲方目录播种。"""
    from app.domain.names import name_key

    for table in ("suppliers", "supplier_profiles"):
        for row in conn.execute("SELECT id, name FROM %s" % table).fetchall():
            conn.execute("UPDATE %s SET name_key=? WHERE id=?" % table,
                         (name_key(row["name"]), row["id"]))

    conn.execute(
        "INSERT OR IGNORE INTO supplier_party_terms"
        "(supplier_name, party_a, start_date, end_date, note, updated_at) "
        "SELECT supplier_name, '', start_date, end_date, note, updated_at "
        "FROM supplier_contract_terms"
    )

    groups = {}
    for row in conn.execute("SELECT * FROM suppliers ORDER BY id").fetchall():
        groups.setdefault(row["name_key"], []).append(row)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        keep = max(rows, key=lambda row: (row["contract_count"], len(row["name"]), -row["id"]))
        for dup in rows:
            if dup["id"] != keep["id"]:
                _merge_supplier_rows(conn, keep, dup)
        conn.execute(
            "UPDATE suppliers SET contract_count=?, main_contract_date=? WHERE id=?",
            (sum(row["contract_count"] for row in rows),
             max((row["main_contract_date"] or "") for row in rows), keep["id"]),
        )

    groups = {}
    for row in conn.execute("SELECT * FROM supplier_profiles ORDER BY id").fetchall():
        groups.setdefault(row["name_key"], []).append(row)
    for rows in groups.values():
        if len(rows) < 2:
            continue
        keep = dict(max(rows, key=lambda row: (row["last_sign"] or "", len(row["name"]),
                                              -row["id"])))
        for dup in rows:
            if dup["id"] == keep["id"]:
                continue
            for column in _PROFILE_TEXT_COLUMNS:
                if not str(keep[column] or "").strip() and str(dup[column] or "").strip():
                    keep[column] = dup[column]
            if (dup["last_sign"] or "") > (keep["last_sign"] or ""):
                keep["last_sign"] = dup["last_sign"]
            conn.execute("DELETE FROM supplier_profiles WHERE id=?", (dup["id"],))
        conn.execute(
            "UPDATE supplier_profiles SET %s WHERE id=?" %
            ", ".join("%s=?" % column for column in _PROFILE_TEXT_COLUMNS + ("last_sign",)),
            [keep[column] for column in _PROFILE_TEXT_COLUMNS + ("last_sign",)] + [keep["id"]],
        )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_suppliers_name_key "
        "ON suppliers(name_key) WHERE name_key <> ''"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contracts_party_a ON contracts(party_a)")
    for name, payload in PARTY_A_SEED.items():
        conn.execute(
            "INSERT OR IGNORE INTO party_a_profiles(name, payload) VALUES(?, ?)",
            (name, json.dumps(payload, ensure_ascii=False)),
        )


def repair_supplier_names(conn):
    """再次执行名称归一与精确合并；已升级的库每次启动都可安全调用。"""
    _m4_party_a_and_name_key(conn)


MIGRATIONS = [
    (3, "drop_legacy_tables", _m3_drop_legacy),
    (4, "party_a_and_name_key", _m4_party_a_and_name_key),
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
