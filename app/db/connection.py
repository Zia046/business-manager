"""Encrypted local database.

Two backends, same API:
  1. SQLCipher (sqlcipher3) - real page-level encryption, preferred on Windows.
  2. Fallback - SQLite lives in RAM; every commit writes the whole database,
     encrypted with Fernet (AES-128-CBC + HMAC), atomically to disk.
     No plaintext database ever touches the disk.

The key is derived from the admin password with PBKDF2-HMAC-SHA256.
The (non-secret) salt is stored next to the database.
"""
import base64
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .schema import SCHEMA_SQL, SCHEMA_VERSION, migrate

try:  # optional dependency
    import sqlcipher3  # type: ignore
except Exception:  # pragma: no cover
    sqlcipher3 = None

PBKDF2_ITERATIONS = 200_000
DB_FILE = "business.bmdb"
SALT_FILE = "key.salt"


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class WrongPasswordError(Exception):
    pass


def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                               PBKDF2_ITERATIONS, dklen=32)


class Database:
    def __init__(self, data_dir: Path, password: str, create: bool = False):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / DB_FILE
        self.salt_path = self.data_dir / SALT_FILE
        self.backend = "sqlcipher" if sqlcipher3 else "fernet"
        self._open(password, create)

    # ---------- opening ----------
    @staticmethod
    def exists(data_dir: Path) -> bool:
        return (Path(data_dir) / DB_FILE).exists()

    def _open(self, password: str, create: bool):
        if create:
            salt = os.urandom(16)
            self.salt_path.write_bytes(salt)
        else:
            if not (self.path.exists() and self.salt_path.exists()):
                raise FileNotFoundError("Database not found")
            salt = self.salt_path.read_bytes()
        self._key = derive_key(password, salt)

        if self.backend == "sqlcipher":
            self.conn = sqlcipher3.connect(str(self.path), isolation_level=None)
            self.conn.execute(f"PRAGMA key = \"x'{self._key.hex()}'\"")
            try:
                self.conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            except Exception as exc:
                raise WrongPasswordError() from exc
        else:
            self._fernet = Fernet(base64.urlsafe_b64encode(self._key))
            self.conn = sqlite3.connect(":memory:", isolation_level=None)
            if not create:
                try:
                    raw = self._fernet.decrypt(self.path.read_bytes())
                except InvalidToken as exc:
                    raise WrongPasswordError() from exc
                self.conn.deserialize(raw)
        self.conn.row_factory = _dict_factory
        self.conn.execute("PRAGMA foreign_keys = ON")
        if create:
            self.conn.executescript(SCHEMA_SQL)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._persist()
        elif self.conn.execute("PRAGMA user_version").fetchone()["user_version"] < SCHEMA_VERSION:
            migrate(self.conn)       # database from an older version of the program
            self._persist()

    # ---------- persistence ----------
    def _persist(self):
        """Fallback backend: write encrypted snapshot atomically."""
        if self.backend != "fernet":
            return
        blob = self._fernet.encrypt(self.conn.serialize())
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, self.path)

    @contextmanager
    def transaction(self):
        """All-or-nothing unit of work (stock + ledger + cash never diverge)."""
        self.conn.execute("BEGIN")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self._persist()

    # ---------- helpers ----------
    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql, params=(), default=0):
        r = self.conn.execute(sql, params).fetchone()
        if not r:
            return default
        v = next(iter(r.values()))
        return default if v is None else v

    def rekey(self, new_password: str):
        """Change the encryption key (used by Change Password)."""
        salt = os.urandom(16)
        new_key = derive_key(new_password, salt)
        if self.backend == "sqlcipher":
            self.conn.execute(f"PRAGMA rekey = \"x'{new_key.hex()}'\"")
        else:
            self._fernet = Fernet(base64.urlsafe_b64encode(new_key))
        self._key = new_key
        self.salt_path.write_bytes(salt)
        self._persist()

    def close(self):
        if self.conn is None:
            return
        self._persist()
        self.conn.close()
        self.conn = None
