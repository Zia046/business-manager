"""Database schema.

Design notes
- Stock is never stored as a single editable number: it is opening_stock plus
  the sum of stock_moves. Every sale/purchase/return writes a move, so cancel
  = delete the moves of that document. Stock can never drift.
- Party balances work the same way via the `ledger` table:
    customer balance = opening + SUM(debit - credit)   (positive = customer owes us)
    supplier balance = opening + SUM(credit - debit)   (positive = we owe supplier)
- Cash in hand = SUM(cash_book in) - SUM(cash_book out).
"""

V3_TABLES = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, user TEXT, action TEXT NOT NULL, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(date);

CREATE TABLE IF NOT EXISTS installment_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
    party_id INTEGER NOT NULL REFERENCES parties(id),
    invoice_id INTEGER REFERENCES invoices(id),
    principal REAL NOT NULL,                        -- amount to be paid in installments
    count INTEGER NOT NULL, note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','cancelled'))
);
CREATE TABLE IF NOT EXISTS installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES installment_plans(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, due_date TEXT NOT NULL,
    amount REAL NOT NULL, paid REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_installments_due ON installments(due_date);

CREATE TABLE IF NOT EXISTS repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
    customer_name TEXT NOT NULL, phone TEXT,
    device TEXT NOT NULL, imei TEXT, problem TEXT,
    estimate REAL NOT NULL DEFAULT 0,
    charges REAL NOT NULL DEFAULT 0,                -- final amount asked from the customer
    parts_cost REAL NOT NULL DEFAULT 0,
    received REAL NOT NULL DEFAULT 0,               -- cash taken so far (advance + final)
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received','in_progress','ready','delivered','cancelled')),
    delivered_date TEXT, note TEXT
);
"""

SCHEMA_SQL = """
CREATE TABLE company (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL,
    email TEXT NOT NULL, logo_path TEXT,
    opening_cash REAL NOT NULL DEFAULT 0,
    slogan TEXT NOT NULL DEFAULT 'Complete Business Management Solution'
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    login_id TEXT NOT NULL UNIQUE,
    pass_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',             -- 'owner' or 'staff'
    name TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,          -- system generated numeric ID
    kind TEXT NOT NULL CHECK (kind IN ('customer','supplier')),
    name TEXT NOT NULL,
    phone TEXT, address TEXT,
    opening_balance REAL NOT NULL DEFAULT 0,
    is_walkin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_parties_kind_name ON parties(kind, name);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT, tags TEXT, unit TEXT DEFAULT 'pcs',
    last_purchase_price REAL NOT NULL DEFAULT 0,
    avg_cost REAL NOT NULL DEFAULT 0,               -- weighted average cost
    sale_price REAL NOT NULL DEFAULT 0,
    opening_stock REAL NOT NULL DEFAULT 0,
    low_stock_level REAL NOT NULL DEFAULT 0,
    track_serial INTEGER NOT NULL DEFAULT 0,        -- 1 for mobile phones (IMEI tracked)
    imei_mode TEXT NOT NULL DEFAULT 'single',       -- 'single' or 'double' IMEI phone
    warranty_months INTEGER NOT NULL DEFAULT 0,     -- default warranty given on sale (0 = none)
    barcode TEXT,                                   -- optional: printed on labels, found by a scanner
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_products_name ON products(name);

CREATE TABLE serials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    serial TEXT NOT NULL UNIQUE,                    -- IMEI 1
    imei2 TEXT,                                     -- IMEI 2 (double-IMEI phones)
    status TEXT NOT NULL DEFAULT 'in_stock' CHECK (status IN ('in_stock','sold')),
    purchase_id INTEGER, invoice_id INTEGER
);

CREATE TABLE counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,                              -- ISO yyyy-mm-dd hh:mm:ss
    party_id INTEGER NOT NULL REFERENCES parties(id),
    subtotal REAL NOT NULL, discount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL, paid REAL NOT NULL DEFAULT 0,
    cost_total REAL NOT NULL DEFAULT 0,              -- cost of goods sold
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled'))
);
CREATE INDEX idx_invoices_date ON invoices(date);
CREATE INDEX idx_invoices_party ON invoices(party_id);

CREATE TABLE invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty REAL NOT NULL, price REAL NOT NULL, discount REAL NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0, serial TEXT, serial2 TEXT,
    warranty_months INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
    party_id INTEGER NOT NULL REFERENCES parties(id),
    total REAL NOT NULL, paid REAL NOT NULL DEFAULT 0, note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled'))
);

CREATE TABLE purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty REAL NOT NULL, price REAL NOT NULL, serial TEXT
);

CREATE TABLE returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('sale','purchase')),
    date TEXT NOT NULL,
    party_id INTEGER NOT NULL REFERENCES parties(id),
    ref_doc_id INTEGER,                              -- original invoice/purchase (optional)
    total REAL NOT NULL, refunded REAL NOT NULL DEFAULT 0, note TEXT
);

CREATE TABLE return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty REAL NOT NULL, price REAL NOT NULL, unit_cost REAL NOT NULL DEFAULT 0
);

CREATE TABLE stock_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    date TEXT NOT NULL,
    qty REAL NOT NULL,                               -- + in, - out
    unit_cost REAL NOT NULL DEFAULT 0,
    ref_type TEXT NOT NULL, ref_id INTEGER NOT NULL, note TEXT
);
CREATE INDEX idx_moves_product ON stock_moves(product_id);
CREATE INDEX idx_moves_ref ON stock_moves(ref_type, ref_id);

CREATE TABLE ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER NOT NULL REFERENCES parties(id),
    date TEXT NOT NULL,
    debit REAL NOT NULL DEFAULT 0, credit REAL NOT NULL DEFAULT 0,
    ref_type TEXT NOT NULL, ref_id INTEGER NOT NULL, note TEXT
);
CREATE INDEX idx_ledger_party ON ledger(party_id);
CREATE INDEX idx_ledger_ref ON ledger(ref_type, ref_id);

CREATE TABLE cash_book (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in','out')),
    amount REAL NOT NULL CHECK (amount > 0),
    party_id INTEGER REFERENCES parties(id),
    ref_type TEXT NOT NULL, ref_id INTEGER NOT NULL, note TEXT
);
CREATE INDEX idx_cash_date ON cash_book(date);
CREATE INDEX idx_cash_ref ON cash_book(ref_type, ref_id);

CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, category TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0), note TEXT
);

CREATE TABLE vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('receipt','payment')),
    date TEXT NOT NULL, party_id INTEGER REFERENCES parties(id),
    amount REAL NOT NULL, ref_type TEXT, ref_id INTEGER, note TEXT
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    is_mobile INTEGER NOT NULL DEFAULT 0,           -- 1 = phones: IMEI numbers are compulsory
    is_system INTEGER NOT NULL DEFAULT 0            -- 1 = cannot be deleted
);
INSERT INTO categories(name,is_mobile,is_system) VALUES
    ('Mobile Phone',1,1),('Accessories',0,0),('Contagious',0,0),('Disposable',0,0),('Other',0,1);
CREATE UNIQUE INDEX idx_serials_imei2 ON serials(imei2) WHERE imei2 IS NOT NULL;
"""

SCHEMA_SQL += V3_TABLES

SCHEMA_VERSION = 3


def migrate(conn):
    """Bring a database made by an older version up to date. Safe to run many times."""
    def cols(table):
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    for table, col, ddl in (("products", "imei_mode", "TEXT NOT NULL DEFAULT 'single'"),
                            ("serials", "imei2", "TEXT"),
                            ("invoice_items", "serial2", "TEXT")):
        if col not in cols(table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    conn.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "name TEXT NOT NULL UNIQUE COLLATE NOCASE, is_mobile INTEGER NOT NULL DEFAULT 0, "
                 "is_system INTEGER NOT NULL DEFAULT 0)")
    if conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"] == 0:
        conn.execute("INSERT INTO categories(name,is_mobile,is_system) VALUES "
                     "('Mobile Phone',1,1),('Accessories',0,0),('Contagious',0,0),('Disposable',0,0),('Other',0,1)")
    for table, col, ddl in (("users", "role", "TEXT NOT NULL DEFAULT 'owner'"), ("users", "name", "TEXT"),
                            ("users", "active", "INTEGER NOT NULL DEFAULT 1"),
                            ("products", "warranty_months", "INTEGER NOT NULL DEFAULT 0"),
                            ("products", "barcode", "TEXT"),
                            ("company", "slogan", "TEXT NOT NULL DEFAULT 'Complete Business Management Solution'"),
                            ("invoice_items", "warranty_months", "INTEGER NOT NULL DEFAULT 0")):
        have = cols(table)
        if have and col not in have:              # (a table that does not exist at all is left alone)
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    for stmt in V3_TABLES.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_serials_imei2 ON serials(imei2) WHERE imei2 IS NOT NULL")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
